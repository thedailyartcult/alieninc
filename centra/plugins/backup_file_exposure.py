"""
Plugin 1133: Backup/Sensitive File Exposure Detection
=======================================================
Detects exposed backup and temporary files on web servers.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class BackupFileExposure(NaslPlugin):
    PLUGIN_ID = 1133
    NAME = 'Backup/Sensitive File Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects exposed backup and temporary files including .bak, .old, .swp, '
        '.sql, .tar.gz, ~ files, and common backup naming patterns. These files '
        'may contain database dumps, source code, or configuration that should '
        'not be publicly accessible.'
    )
    SOLUTION = (
        'Block backup file patterns via web server. Never store backups in web '
        'root. Use access controls on backup directories.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    BACKUP_PATHS = [
        '/backup.sql', '/dump.sql', '/db.sql', '/database.sql',
        '/backup.tar.gz', '/backup.zip', '/backup.tar.bz2',
        '/site.tar.gz', '/www.tar.gz', '/htdocs.tar.gz',
        '/.htaccess.bak', '/.htaccess.old', '/.htaccess.swp',
        '/index.php.bak', '/index.php.old', '/index.php~',
        '/wp-config.php.bak', '/wp-config.php.old',
        '/config.php.bak', '/config.php.old', '/config.php~',
        '/.env.bak', '/.env.old', '/.env.swp',
        '/composer.json.bak', '/package.json.bak',
        '/app.bak', '/app.old', '/app.tar.gz', '/app.zip',
        '/dump.rdb', '/backup/',
        '/private/', '/_private/', '/_backup/',
        '~', '*.bak', '*.old', '*.swp', '*.orig',
    ]

    EXTENSION_PATTERNS = [
        '.bak', '.old', '.swp', '.orig', '.backup',
        '.save', '.tmp', '.temp', '.copy', '.dmp',
        '~',
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

                discovered_pages = await self._discover_pages(target, p, ctx)

                exposed = []

                for path in self.BACKUP_PATHS[:20]:
                    body, status = await self._fetch_path(target, p, path, ctx)
                    if body and status and '200' in status and len(body) > 5:
                        size = len(body)
                        content_type = b'text/html' not in body[:500]
                        if content_type or path.endswith(('.sql', '.tar.gz', '.zip', '.bak', '.old')):
                            exposed.append(f'{path} ({size}b)')
                            if len(exposed) >= 10:
                                break

                for page in discovered_pages[:10]:
                    for ext in self.EXTENSION_PATTERNS:
                        backup_path = page + ext
                        body, status = await self._fetch_path(target, p, backup_path, ctx)
                        if body and status and '200' in status and len(body) > 5:
                            size = len(body)
                            exposed.append(f'{backup_path} ({size}b)')
                            if len(exposed) >= 10:
                                break
                    if len(exposed) >= 10:
                        break

                if exposed:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'Backup/temporary file exposure: {len(exposed)} file(s) accessible',
                        solution=self.SOLUTION,
                        evidence='; '.join(exposed),
                        references=[
                            'https://owasp.org/www-community/attacks/Backup_File_Exposure',
                            'https://www.tenable.com/plugins/nessus/10428',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No backup file exposure detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _discover_pages(self, target: str, port: int, ctx: ssl.SSLContext | None) -> list[str]:
        pages = []
        body = await self._fetch_body(target, port, '/', ctx)
        if body:
            import re
            hrefs = re.findall(rb'href=["\']([^"\']+)["\']', body)
            for h in hrefs:
                h_str = h.decode(errors='ignore').split('?')[0]
                if h_str.endswith(('.php', '.html', '.htm', '.asp', '.aspx', '.jsp')):
                    if h_str not in pages and not h_str.startswith('http'):
                        pages.append('' if h_str.startswith('/') else '/' + h_str)
        return pages

    async def _fetch_body(self, target: str, port: int, path: str, ctx: ssl.SSLContext | None) -> bytes | None:
        body, _ = await self._fetch_path(target, port, path, ctx)
        return body

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
