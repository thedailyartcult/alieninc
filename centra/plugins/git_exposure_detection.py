"""
Plugin 1131: Git Repository Exposure Detection
================================================
Detects exposed Git repository metadata via /.git directories.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GitExposureDetection(NaslPlugin):
    PLUGIN_ID = 1131
    NAME = 'Git Repository Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects exposed Git repository metadata via /.git directories. '
        'Accessible Git repositories reveal full source code, commit history, '
        'credentials in commit messages, database configurations, API keys, '
        'and other sensitive data embedded in the codebase.'
    )
    SOLUTION = (
        'Block /.git paths via web server configuration. Do not deploy .git '
        'directory to production. Remove .git from web root.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    GIT_PATHS = [
        '/.git/HEAD',
        '/.git/config',
        '/.git/objects/',
        '/.git/index',
        '/.git/refs/heads/master',
        '/.git/refs/heads/main',
        '/.git/logs/HEAD',
        '/.gitignore',
        '/.gitattributes',
        '/.git/packed-refs',
        '/.git/description',
        '/.git/info/exclude',
    ]

    GIT_SIGNATURES = [
        b'ref: refs/heads/',
        b'[core]',
        b'repositoryformatversion',
        b'xK\x0c\xae\xd0',
        b'DIRC',
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

                accessible = []

                for path in self.GIT_PATHS:
                    body, status = await self._fetch_path(target, p, path, ctx)
                    if status and '200' in status and body:
                        matched = any(sig in body for sig in self.GIT_SIGNATURES)
                        if matched:
                            size = len(body)
                            accessible.append(f'{path} ({size}b)')
                            if len(accessible) >= 5:
                                break

                if accessible:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='critical',
                        description=f'Git repository exposed: {len(accessible)} path(s) accessible',
                        solution=self.SOLUTION,
                        evidence='; '.join(accessible),
                        references=[
                            'https://owasp.org/www-community/attacks/Git_Repository_Exposure',
                            'https://www.tenable.com/plugins/nessus/10428',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No Git repository exposure detected'
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
