import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class WSOriginBypassDetection(NaslPlugin):
    PLUGIN_ID = 1215
    NAME = 'WebSocket Origin Validation Bypass'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects WebSocket endpoints that fail to validate the Origin header during the WebSocket upgrade handshake. Missing or weak origin validation allows cross-origin WebSocket connections, enabling data theft and unauthorized actions via CSWSH (Cross-Site WebSocket Hijacking).'
    SOLUTION = 'Validate Origin header against a whitelist. Require authentication tokens in the WebSocket connection URL or during handshake. Use same-origin policy for WebSocket connections.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ws_endpoints = ['/', '/ws', '/websocket', '/socket', '/chat', '/api/ws', '/ws/connect']
        import hashlib, base64
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

                for endpoint in ws_endpoints:
                    key = base64.b64encode(hashlib.sha1(str(id(endpoint)).encode()).digest()[:16]).decode()
                    req = (
                        f'GET {endpoint} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Upgrade: websocket\r\n'
                        f'Connection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {key}\r\n'
                        f'Sec-WebSocket-Version: 13\r\n'
                        f'Origin: https://evil.com\r\n\r\n'
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
                            if len(resp) > 4096: break
                    except asyncio.TimeoutError:
                        pass
                    writer.close()
                    await writer.wait_closed()

                    if resp and b'101' in resp[:6] and b'Switching Protocols' in resp[:64]:
                        results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'WebSocket endpoint {endpoint} accepted upgrade with malicious Origin: https://evil.com'))
                        return results
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No vulnerable WebSocket endpoint detected'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
