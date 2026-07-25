"""
Plugin 1130: JavaScript Source Map Exposure
=============================================
Detects exposed JavaScript source map files (.map) that reveal original source.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class SourceMapExposure(NaslPlugin):
    PLUGIN_ID = 1130
    NAME = 'JavaScript Source Map Exposure'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects exposure of JavaScript source map files (.map) that reveal '
        'original source code, including comments, internal API endpoints, '
        'and development-only code. Source maps uploaded to production allow '
        'attackers to reverse-engineer the application logic.'
    )
    SOLUTION = (
        'Do not deploy source maps to production. Use a whitelist to block '
        '.map file access. Configure web server to deny .map file extensions.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SCRIPT_REGEX = re.compile(rb'<script[^>]+src=["\']([^"\']+\.js)[^"\']*["\']', re.IGNORECASE)
    SOURCEMAP_HEADER = re.compile(rb'sourceMappingURL=[\'"]?([^ \n\r]+\.map)')

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

                body = await self._fetch_body(target, p, '/', ctx)
                if body is None:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='Could not retrieve page content'
                    ))
                    continue

                js_paths = self.SCRIPT_REGEX.findall(body)
                js_paths = list(set(p.decode(errors='ignore') for p in js_paths))

                inline_maps = self.SOURCEMAP_HEADER.findall(body)

                exposed = []

                for js_path in js_paths[:20]:
                    if js_path.startswith('//'):
                        js_path = 'https:' + js_path
                    if '?' in js_path:
                        js_path = js_path.split('?')[0]
                    map_path = js_path + '.map' if not js_path.endswith('.map') else js_path

                    map_body = await self._fetch_body(target, p, map_path, ctx)
                    if map_body and b'"sources"' in map_body and b'"mappings"' in map_body:
                        size = len(map_body)
                        exposed.append(f'{map_path} ({size} bytes)')
                        if len(exposed) >= 5:
                            break

                if not exposed:
                    for ref_match in inline_maps:
                        map_path = ref_match.decode(errors='ignore')
                        if not map_path.startswith('/'):
                            map_path = '/' + map_path
                        map_body = await self._fetch_body(target, p, map_path, ctx)
                        if map_body and b'"sources"' in map_body:
                            exposed.append(f'{map_path} (from sourceMappingURL)')
                            if len(exposed) >= 5:
                                break

                if exposed:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Source map exposure: {len(exposed)} .map file(s) accessible',
                        solution=self.SOLUTION,
                        evidence='; '.join(exposed),
                        references=[
                            'https://owasp.org/www-community/attacks/Source_Map_Disclosure',
                            'https://www.tenable.com/plugins/nessus/10656',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No source map files detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _fetch_body(self, target: str, port: int, path: str, ctx: ssl.SSLContext | None) -> bytes | None:
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
                f'Accept: */*\r\n'
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

            status = response.split(b'\r\n')[0].decode(errors='ignore')
            if '200' not in status:
                return None

            _, _, body = response.partition(b'\r\n\r\n')
            return body

        except Exception:
            return None
