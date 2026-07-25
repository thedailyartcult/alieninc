import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class CORSNullOriginDetection(NaslPlugin):
    PLUGIN_ID = 1214
    NAME = 'CORS Null Origin Trust Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects CORS configurations that trust the null origin. The null origin is sent by sandboxed iframes, data: URLs, and file: URLs. If Access-Control-Allow-Origin is set to null, any sandboxed page can make authenticated cross-origin requests to the API.'
    SOLUTION = 'Do not whitelist null in CORS origins. Use explicit domain whitelists. Be aware that some browser extensions may send null origin.'
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
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                req = (
                    f'OPTIONS / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'Origin: null\r\n'
                    f'Access-Control-Request-Method: GET\r\n'
                    f'Connection: close\r\n\r\n'
                )
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                writer.write(req.encode())
                await writer.drain()
                resp = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk: break
                        resp += chunk
                        if len(resp) > 8192: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                vulnerable = False
                if resp:
                    header_section = resp.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in resp else resp
                    header_lower = header_section.lower()
                    if b'access-control-allow-origin: null' in header_lower:
                        vulnerable = True

                if vulnerable:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description='CORS trusts null origin - sandboxed iframes can make authenticated requests'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='CORS does not trust null origin'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
