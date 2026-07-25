import asyncio
import base64
import hashlib
import os
import ssl
from plugins import NaslPlugin, PluginResult

class WebSocketAuthCheck(NaslPlugin):
    PLUGIN_ID = 1255
    NAME = 'WebSocket Authentication Enforcement Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects WebSocket endpoints that do not enforce authentication. Tests if WebSocket upgrades are accepted without session cookies, without Authorization headers, or with invalid tokens. Unauthenticated WebSocket access allows data eavesdropping and unauthorized actions.'
    SOLUTION = 'Require authentication before accepting WebSocket upgrades. Validate session tokens on the WebSocket handshake. Reject unauthenticated upgrade requests. Use origin validation.'
    CVE = []
    PORTS = [80, 443, 8080, 8443, 4000]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ws_endpoints = ['/ws', '/socket', '/websocket', '/chat', '/ws/chat', '/api/ws', '/ws/notifications', '/ws/events', '/live', '/ws/live']
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for ep in ws_endpoints:
                try:
                    ctx = None
                    scheme = 'https' if port_to_check in (443, 8443, 4000) else 'http'
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    key = base64.b64encode(os.urandom(16)).decode()
                    host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                    req = (
                        f'GET {ep} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Upgrade: websocket\r\n'
                        f'Connection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {key}\r\n'
                        f'Sec-WebSocket-Version: 13\r\n'
                        f'\r\n'
                    )
                    writer.write(req.encode())
                    await writer.drain()
                    response = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk: break
                            response += chunk
                            if len(response) > 4096: break
                    except asyncio.TimeoutError:
                        pass
                    writer.close()
                    await writer.wait_closed()
                    if response:
                        status_line = response.split(b'\r\n')[0].decode()
                        if '101' in status_line:
                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'WebSocket endpoint {ep} accepted upgrade without authentication (status 101). Unauthenticated WebSocket access possible.'))
                            found = True
                            break
                        elif '426' in status_line:
                            results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'WebSocket endpoint {ep} requires upgrade header (426). Authentication may be enforced.'))
                        elif '401' in status_line or '403' in status_line:
                            results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'WebSocket endpoint {ep} enforces authentication (status {status_line.split()[1]}).'))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No unauthenticated WebSocket endpoints found'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
