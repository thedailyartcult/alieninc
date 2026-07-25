"""
Plugin 1132: Environment File Exposure Detection
===================================================
Detects exposure of environment/configuration files.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class EnvExposureDetection(NaslPlugin):
    PLUGIN_ID = 1132
    NAME = 'Environment File Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects exposure of environment/configuration files including .env, '
        '.env.production, .env.local, config.php, settings.py, application.yml. '
        'Exposed env files reveal database credentials, API keys, secret keys, '
        'and cloud service credentials.'
    )
    SOLUTION = (
        'Block common config file patterns via web server. Never store .env '
        'files in the web root. Use environment variables instead of config files.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    CONFIG_PATHS = [
        '/.env',
        '/.env.production',
        '/.env.local',
        '/.env.dev',
        '/.env.staging',
        '/.env.backup',
        '/.env.example',
        '/config.php',
        '/settings.py',
        '/application.yml',
        '/application.properties',
        '/config/database.yml',
        '/config/secrets.yml',
        '/config/parameters.yml',
        '/config/app.php',
        '/config.json',
        '/config.dev.json',
        '/config.prod.json',
        '/database.yml',
        '/database.php',
        '/wp-config.php.bak',
        '/.db_password',
        '/config/db.php',
        '/app/config/parameters.yml',
    ]

    SENSITIVE_PATTERNS = [
        rb'(?i)DB_?(?:HOST|NAME|USER|PASSWORD|DATABASE|DRIVER|CONNECTION)\s*[:=]',
        rb'(?i)(?:API|SECRET|AUTH|TOKEN|KEY|PASS|SALT)\s*[:=]\s*["\'][^"\']+["\']',
        rb'(?i)AWS_?(?:ACCESS|SECRET|KEY|BUCKET|REGION|SESSION)\s*[:=]',
        rb'(?i)DATABASE_URL\s*[:=]',
        rb'(?i)REDIS_?(?:URL|HOST|PORT|PASSWORD)\s*[:=]',
        rb'(?i)SECRET_KEY_BASE\s*[:=]',
        rb'(?i)RAILS_MASTER_KEY\s*[:=]',
        rb'(?i)MYSQL_?(?:HOST|DATABASE|USER|PASSWORD)\s*[:=]',
        rb'(?i)POSTGRES_?(?:HOST|DB|USER|PASSWORD)\s*[:=]',
        rb'(?i)MONGO_?(?:HOST|DB|URI|URL)\s*[:=]',
        rb'(?i)STRIPE_?(?:API|SECRET|PUBLIC|KEY|SK|PK)\s*[:=]',
        rb'(?i)SENDGRID_?(?:API|KEY|USER|PASS)\s*[:=]',
        rb'(?i)MAIL_?(?:HOST|USER|PASS|PASSWORD|DRIVER|ENCRYPTION)\s*[:=]',
        rb'(?i)OAUTH_?(?:TOKEN|CLIENT|SECRET|ID)\s*[:=]',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ports = self.PORTS if port is None else [port]

        for p in ports:
            try:
                scheme = 'https' if p in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                exposed = []

                for path in self.CONFIG_PATHS:
                    body, status = await self._fetch_path(target, p, path, ctx)
                    if status and '200' in status and body and len(body) > 10:
                        matched = any(re.search(pat, body) for pat in self.SENSITIVE_PATTERNS)
                        if matched:
                            kind = 'config' if path.endswith(('.yml', '.yaml', '.properties', '.json', '.php', '.py')) else 'env'
                            size = len(body)
                            sample = body[:120].decode(errors='ignore').replace('\n', ' ').strip()
                            exposed.append(f'{path} ({kind}, {size}b): {sample[:60]}')
                            if len(exposed) >= 5:
                                break

                if exposed:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='critical',
                        description=f'Environment/config file exposure: {len(exposed)} file(s) with sensitive data',
                        solution=self.SOLUTION,
                        evidence='; '.join(exposed),
                        references=[
                            'https://owasp.org/www-community/attacks/Configuration_File_Exposure',
                            'https://www.tenable.com/plugins/nessus/10428',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No environment file exposure detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _fetch_path(self, target: str, port: int, path: str, ctx: ssl.SSLContext | None) -> tuple[bytes, str | None]:
        try:
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 65536:
                    break

            writer.close()
            await writer.wait_closed()

            status_line = response.split(b'\r\n')[0].decode(errors='ignore')
            _, _, body = response.partition(b'\r\n\r\n')
            return body, status_line

        except Exception:
            return b'', None
