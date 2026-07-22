"""
Plugin 1004: Exposed Sensitive Files Check
============================================
Scans for publicly accessible sensitive files.
Real CVEs: CVE-2023-38408 (exposed SSH configs), CVE-2020-14882 (WebLogic console)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class ExposedFiles(NaslPlugin):
    PLUGIN_ID = 1004
    NAME = 'Exposed Sensitive Files'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'One or more sensitive files are publicly accessible via HTTP. '
        'This may include environment files, version control metadata, '
        'configuration files, or backup archives.'
    )
    SOLUTION = (
        'Restrict access to sensitive files via server configuration. '
        'Remove files from production deployments. Use .htaccess, nginx rules, '
        'or cloud CDN rules to block access to dotfiles and backup archives.'
    )
    CVE = ['CVE-2023-38408', 'CVE-2020-14882']
    PORTS = [80, 443]

    SENSITIVE_PATHS = [
        ('/.git/config', 'Git configuration', 'critical'),
        ('/.git/HEAD', 'Git HEAD pointer', 'critical'),
        ('/.env', 'Environment variables', 'critical'),
        ('/.env.production', 'Production environment', 'critical'),
        ('/.env.backup', 'Environment backup', 'critical'),
        ('/.env.local', 'Local environment', 'critical'),
        ('/.htaccess', 'Apache configuration', 'high'),
        ('/.htpasswd', 'Apache password file', 'critical'),
        ('/wp-config.php', 'WordPress configuration', 'critical'),
        ('/config/database.yml', 'Database configuration', 'critical'),
        ('/config/secrets.yml', 'Secrets configuration', 'critical'),
        ('/server-status', 'Apache server status', 'high'),
        ('/server-info', 'Apache server info', 'high'),
        ('/phpmyadmin/', 'phpMyAdmin', 'critical'),
        ('/backup/', 'Backup directory', 'high'),
        ('/dump/', 'Data dump directory', 'high'),
        ('/.ssh/authorized_keys', 'SSH authorized keys', 'critical'),
        ('/.aws/credentials', 'AWS credentials', 'critical'),
        ('/composer.json', 'Composer configuration', 'medium'),
        ('/package.json', 'NPM configuration', 'low'),
        ('/.DS_Store', 'macOS metadata', 'medium'),
        ('/Thumbs.db', 'Windows thumbnails', 'low'),
        ('/web.config', 'IIS configuration', 'high'),
        ('/elmah.axd', 'Error log', 'high'),
        ('/trace.axd', 'ASP.NET trace', 'high'),
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        results = []
        found_files = []

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            for path, name, severity in self.SENSITIVE_PATHS:
                req = f'GET {path} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()

                resp = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        resp += chunk
                        if len(resp) > 8192:
                            break
                except asyncio.TimeoutError:
                    pass

                status_line = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')

                if any(s in status_line for s in ['200 OK', '201 Created', '200 ']):
                    if '403 Forbidden' not in status_line and '404' not in status_line:
                        found_files.append((path, name, severity))

            writer.close()
            await writer.wait_closed()

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description=f'HTTP port {port} not reachable')]

        if found_files:
            max_sev = 'info'
            sev_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
            for _, _, sev in found_files:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev

            file_list = ', '.join([f'{name} ({path})' for path, name, _ in found_files])

            cvss_map = {'critical': 7.5, 'high': 5.3, 'medium': 3.1, 'low': 1.5}
            cvss = cvss_map.get(max_sev, 1.0)

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description=f'{len(found_files)} sensitive file(s) exposed: {file_list}',
                solution=self.SOLUTION,
                evidence=f'Accessible files: {file_list}',
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-38408',
                    'https://www.tenable.com/plugins/nessus/10428',
                ]
            ))
        else:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description='No sensitive files detected'
            ))

        return results
