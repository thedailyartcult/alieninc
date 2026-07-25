"""
Plugin 1128: Debug Mode / Information Leak Detection
=======================================================
Probes for debug and development endpoints that leak sensitive data.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class DebugModeDetection(NaslPlugin):
    PLUGIN_ID = 1128
    NAME = 'Debug Mode / Information Leak Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects debug or development mode endpoints that expose sensitive '
        'information. Probes for /debug, /dev, /info, /status, /health, '
        '/metrics, /api/docs, /redoc, /swagger, /api/v1/docs — which may '
        'reveal source code, configuration, environment variables, or '
        'database credentials.'
    )
    SOLUTION = (
        'Disable debug mode in production. Remove development endpoints. '
        'Use authentication for admin/debug endpoints. Strip detailed error pages.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    DEBUG_PATHS = [
        '/debug', '/debug/', '/dev', '/dev/',
        '/info', '/status', '/health', '/metrics',
        '/api/docs', '/redoc', '/swagger', '/api/v1/docs',
        '/api/v2/docs', '/docs', '/console',
        '/phpinfo.php', '/info.php', '/test.php',
        '/actuator', '/actuator/health', '/actuator/info',
        '/.env', '/config', '/api/config',
    ]

    DEBUG_INDICATORS = [
        b'debug', b'development', b'stack trace', b'traceback',
        b'env', b'DATABASE_URL', b'db_password', b'db_user',
        b'API_KEY', b'SECRET_KEY', b'password', b'credentials',
        b'openapi', b'swagger', b'swagger-ui', b'redoc',
        b'actuator', b'health check', b'"status":"UP"',
        b'PHP Version', b'PHP Credits', b'Symfony',
        b'Laravel', b'Django', b'Flask', b'Express',
        b'Spring', b'application/json', b'{"status"',
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

                found = []

                for path in self.DEBUG_PATHS:
                    body, status = await self._fetch_path(target, p, path, ctx)
                    if status and '200' in status:
                        matches = [d for d in self.DEBUG_INDICATORS if d.lower() in body.lower()]
                        if matches:
                            found.append(f'{path}: {matches[0].decode(errors="ignore")[:40]}')
                            if len(found) >= 5:
                                break

                if found:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'Debug/development endpoint(s) exposed: {len(found)} path(s)',
                        solution=self.SOLUTION,
                        evidence='; '.join(found),
                        references=[
                            'https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/',
                            'https://www.tenable.com/plugins/nessus/45590',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No debug/development endpoints detected'
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
