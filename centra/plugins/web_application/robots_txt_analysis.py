"""
Plugin 1150: Robots.txt Sensitive Path Discovery
===================================================
Analyzes robots.txt for sensitive paths that the site attempts to hide.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class RobotsTxtAnalysis(NaslPlugin):
    PLUGIN_ID = 1150
    NAME = 'Robots.txt Sensitive Path Discovery'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Analyzes robots.txt for sensitive paths that the site attempts to hide '
        'from crawlers. While robots.txt is a voluntary standard, the paths listed '
        'in Disallow directives often reveal admin panels, internal tools, or '
        'sensitive directories that attackers will target.'
    )
    SOLUTION = (
        'Do not rely on robots.txt for security. Use proper authentication for '
        'sensitive paths. Remove internal-only paths from public robots.txt.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATTERNS = [
        (r'admin', 'Admin panel'),
        (r'login', 'Login page'),
        (r'wp-admin', 'WordPress admin'),
        (r'/api/', 'API endpoint'),
        (r'backup', 'Backup directory'),
        (r'config', 'Configuration'),
        (r'db[-_]?', 'Database'),
        (r'sql', 'SQL-related'),
        (r'secret', 'Secrets'),
        (r'internal', 'Internal tool'),
        (r'private', 'Private content'),
        (r'debug', 'Debug interface'),
        (r'console', 'Console access'),
        (r'dashboard', 'Dashboard'),
        (r'\.git', 'Git repository'),
        (r'\.env', 'Environment file'),
        (r'\.ssh', 'SSH keys'),
        (r'cron', 'Cron jobs'),
        (r'log[-_]?', 'Log files'),
        (r'upload', 'Upload directory'),
        (r'export', 'Export/backup'),
        (r'dev', 'Development area'),
        (r'staging', 'Staging environment'),
        (r'test', 'Test content'),
        (r'shell', 'Shell access'),
        (r'phpmyadmin', 'phpMyAdmin'),
        (r'manager', 'Management interface'),
        (r'server-status', 'Apache server status'),
        (r'server-info', 'Apache server info'),
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                req = f'GET /robots.txt HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()

                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 32768:
                        break

                writer.close()
                await writer.wait_closed()

                header_section, _, body = response.partition(b'\r\n\r\n')
                status_line = header_section.decode('utf-8', errors='ignore').split('\r\n')[0] if header_section else ''
                status_code = 0
                if status_line:
                    try:
                        status_code = int(status_line.split(' ')[1])
                    except (IndexError, ValueError):
                        pass

                if status_code != 200 or not body:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='No robots.txt found (or access forbidden)'
                    ))
                    continue

                body_text = body.decode('utf-8', errors='ignore')

                disallow_paths = re.findall(r'^disallow:\s*(.*?)\s*$', body_text, re.MULTILINE | re.IGNORECASE)
                disallow_paths = [p for p in disallow_paths if p and not p == '/']

                if not disallow_paths:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='robots.txt found but no Disallow directives with paths'
                    ))
                    continue

                sensitive_findings = []
                for path in disallow_paths:
                    for pattern, label in self.SENSITIVE_PATTERNS:
                        if re.search(pattern, path, re.IGNORECASE):
                            sensitive_findings.append(f'{label}: {path}')
                            break

                if sensitive_findings:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='low',
                        description=f'sensitive path(s) exposed in robots.txt: {len(sensitive_findings)} found',
                        solution=self.SOLUTION,
                        evidence='; '.join(sensitive_findings[:10]),
                        references=[
                            'https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt',
                            'https://www.tenable.com/plugins/nessus/10656',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'robots.txt found with {len(disallow_paths)} disallowed path(s), none flagged as sensitive'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='Port not reachable'
                ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ports reachable for robots.txt check'
            ))

        return results
