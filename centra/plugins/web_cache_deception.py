import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class WebCacheDeception(NaslPlugin):
    PLUGIN_ID = 1202
    NAME = 'Web Cache Deception Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects web cache deception vulnerabilities where adding a static-like path extension (;/test.css, ?test.css, /nonexistent.css) to a sensitive URL causes the response to be cached as static content. An attacker can then access the cached sensitive data.'
    SOLUTION = 'Configure cache to ignore query strings. Use explicit cache rules based on content type not path. Do not cache authenticated responses. Use Vary: Cookie or Vary: Authorization headers.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATHS = ['/api/user', '/dashboard', '/account', '/profile', '/admin', '/api/data', '/user/settings']

    DECEPTION_APPENDS = [
        '/nonexistent.css',
        '/nonexistent.js',
        ';.css',
        ';.js',
        '?.css',
        '?.js',
        '/test.css',
        '/test.js',
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

                for path in self.SENSITIVE_PATHS:
                    original_response = None
                    try:
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host_header = 'alieninc.tech'

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()

                        original_response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk: break
                                original_response += chunk
                                if len(original_response) > 8192: break
                        except asyncio.TimeoutError:
                            pass

                        writer.close()
                        await writer.wait_closed()
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

                    if not original_response:
                        continue

                    for append in self.DECEPTION_APPENDS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            deceived_path = f'{path}{append}'
                            req = f'GET {deceived_path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                            writer.write(req.encode())
                            await writer.drain()

                            deceived_response = b''
                            try:
                                while True:
                                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                    if not chunk: break
                                    deceived_response += chunk
                                    if len(deceived_response) > 8192: break
                            except asyncio.TimeoutError:
                                pass

                            writer.close()
                            await writer.wait_closed()

                            if deceived_response and original_response:
                                orig_body = original_response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in original_response else original_response
                                dec_body = deceived_response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in deceived_response else deceived_response

                                if orig_body == dec_body and len(dec_body) > 100:
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='medium',
                                        description=f'Web cache deception detected on {path} using append "{append}" - identical response body',
                                        solution=self.SOLUTION,
                                        evidence=f'Original path: {path}, deceived path: {deceived_path}, body size: {len(dec_body)} bytes',
                                        references=['https://owasp.org/www-community/attacks/Cache_Deception']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No web cache deception vulnerabilities detected'))
        return results
