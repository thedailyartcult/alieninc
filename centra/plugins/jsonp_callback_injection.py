import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class JsonpCallbackInjection(NaslPlugin):
    PLUGIN_ID = 1201
    NAME = 'JSONP Callback Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects JSONP callback injection vulnerabilities by injecting arbitrary callback function names via the callback parameter. Unsanitized JSONP callbacks can be exploited for cross-site scripting and data theft via the JSONP endpoint.'
    SOLUTION = 'Validate callback parameter against a strict regex (alphanumeric only). Use a fixed callback name. Migrate from JSONP to CORS-based cross-origin requests.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    JSONP_PATHS = ['/api/jsonp', '/jsonp', '/api/callback', '/callback', '/api/data', '/data', '/api/users']

    CALLBACK_PAYLOADS = [
        'alert(1)',
        'test',
        'print',
        'console.log',
        'document.cookie',
        'xss',
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

                for path in self.JSONP_PATHS:
                    for cb in self.CALLBACK_PAYLOADS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            req = f'GET {path}?callback={cb} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                                body = response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in response else response
                                body_str = body.decode('utf-8', errors='ignore')
                                content_type = b''
                                header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else b''
                                for line in header_section.split(b'\r\n')[1:]:
                                    if b':' in line:
                                        k, v = line.split(b':', 1)
                                        if k.strip().lower() == b'content-type':
                                            content_type = v.strip()
                                            break

                                is_jsonp = b'javascript' in content_type or b'json' in content_type
                                if is_jsonp or cb in body_str:
                                    if cb in body_str:
                                        results.append(PluginResult(
                                            vulnerable=True, target=target, port=port_to_check,
                                            cvss_score=self.CVSS_SCORE, severity='high',
                                            description=f'JSONP callback injection detected on {path} with callback={cb}',
                                            solution=self.SOLUTION,
                                            evidence=f'Path: {path}, callback: {cb}, callback reflected in response',
                                            references=['https://owasp.org/www-community/attacks/JSONP_Injection']
                                        ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No JSONP callback injection vulnerabilities detected'))
        return results
