import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class CORSCredentialsWildcardDetection(NaslPlugin):
    PLUGIN_ID = 1208
    NAME = 'CORS Credentials with Wildcard Origin'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects CORS configurations that set Access-Control-Allow-Credentials: true together with Access-Control-Allow-Origin: * or a reflected origin. This is a critical misconfiguration that allows any website to make authenticated requests and read responses.'
    SOLUTION = 'Never set Access-Control-Allow-Credentials: true with wildcard or reflected origins. Use explicit origin whitelist when credentials are allowed.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                req = (
                    f'OPTIONS / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'Origin: https://attacker.com\r\n'
                    f'Access-Control-Request-Method: GET\r\n'
                    f'Connection: close\r\n\r\n'
                )
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

                vulnerable = False
                if response:
                    header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else response
                    header_lower = header_section.lower()
                    has_creds = b'access-control-allow-credentials: true' in header_lower
                    has_wildcard_origin = b'access-control-allow-origin: *' in header_lower
                    has_reflected = b'access-control-allow-origin: https://attacker.com' in header_lower
                    if has_creds and (has_wildcard_origin or has_reflected):
                        vulnerable = True

                if vulnerable:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description='CORS configured with credentials=true and wildcard/reflected origin'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No dangerous CORS credentials configuration'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
