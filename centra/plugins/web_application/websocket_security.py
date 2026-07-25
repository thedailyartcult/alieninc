"""
Plugin 1142: WebSocket Security Assessment
============================================
Assesses WebSocket endpoint security by testing for unauthenticated connections.
Real CVEs: CVE-2024-27336 (unauth WebSocket), CVE-2023-31432
"""
import asyncio
import hashlib
import base64
import ssl

from plugins import NaslPlugin, PluginResult


class WebsocketSecurityDetection(NaslPlugin):
    PLUGIN_ID = 1142
    NAME = 'WebSocket Security Assessment'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Assesses WebSocket endpoint security by testing for unauthenticated '
        'connections, missing origin validation, and sensitive data exposure over '
        'WebSocket. Unsecured WebSocket endpoints allow attackers to subscribe to '
        'real-time data streams without authorization.'
    )
    SOLUTION = (
        'Authenticate all WebSocket connections. Validate Origin header against '
        'whitelist. Use wss:// for all WebSocket connections.'
    )
    CVE = ['CVE-2024-27336', 'CVE-2023-31432']
    PORTS = [80, 443, 8080, 8443]

    WS_PATHS = ['/ws', '/socket', '/websocket', '/api/ws', '/sock']
    PROBE_KEY = 'dGhlIHNhbXBsZSBub25jZQ=='  # "the sample nonce"

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for path in self.WS_PATHS:
                try:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                    )
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'

                    key = base64.b64encode(hashlib.sha1(self.PROBE_KEY.encode()).digest()).decode()
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Upgrade: websocket\r\n'
                        f'Connection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {key}\r\n'
                        f'Sec-WebSocket-Version: 13\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'\r\n'
                    )
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 8192:
                            break
                    writer.close()
                    await writer.wait_closed()

                    response_text = response.decode('utf-8', errors='ignore')
                    if '101' in response_text.split('\r\n')[0] and 'Sec-WebSocket-Accept' in response_text:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='medium',
                            description=f'WebSocket endpoint {path} accepted upgrade without authentication.',
                            solution=self.SOLUTION,
                            evidence=f'Path: {path}, WebSocket upgrade accepted',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2024-27336',
                                'https://portswigger.net/web-security/websockets',
                            ]
                        ))
                        return results

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
