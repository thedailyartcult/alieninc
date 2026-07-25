import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class CacheableHttpsResponse(NaslPlugin):
    PLUGIN_ID = 1197
    NAME = 'Cacheable HTTPS Response with Sensitive Data'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Detects HTTPS responses containing sensitive data that are marked as cacheable. Even over HTTPS, sensitive data cached by shared proxies or browser caches can be accessed by other users or attackers with local system access.'
    SOLUTION = 'Set Cache-Control: no-store for all responses containing sensitive data. Use private for user-specific responses. Set Expires headers to past dates for sensitive content.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATHS = ['/dashboard', '/account', '/profile', '/admin', '/settings', '/api/user', '/billing']

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

                for path in self.SENSITIVE_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host_header = 'alieninc.tech'

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()

                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk: break
                                response += chunk
                                if len(response) > 8192: break
                        except asyncio.TimeoutError:
                            pass

                        writer.close()
                        await writer.wait_closed()

                        if response:
                            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                            headers = {}
                            for line in header_section.split('\r\n')[1:]:
                                if ':' in line:
                                    key, val = line.split(':', 1)
                                    headers[key.strip().lower()] = val.strip()

                            cc = headers.get('cache-control', '').lower()
                            expires = headers.get('expires', '').lower()
                            pragma = headers.get('pragma', '').lower()

                            is_cacheable = True
                            if 'no-store' in cc or 'private' in cc or 'no-cache' in cc:
                                is_cacheable = False
                            if expires and '0' in expires or 'past' in expires or 'thu, 01 dec' in expires:
                                is_cacheable = False
                            if 'no-cache' in pragma:
                                is_cacheable = False

                            if is_cacheable:
                                results.append(PluginResult(
                                    vulnerable=True, target=target, port=port_to_check,
                                    cvss_score=self.CVSS_SCORE, severity='medium',
                                    description=f'Sensitive path {path} is cacheable and may expose sensitive data',
                                    solution=self.SOLUTION,
                                    evidence=f'Path: {path}, Cache-Control: {cc}, Expires: {expires}',
                                    references=['https://cheatsheetseries.owasp.org/cheatsheets/Cache_Management_Cheat_Sheet.html']
                                ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No cacheable sensitive responses detected'))
        return results
