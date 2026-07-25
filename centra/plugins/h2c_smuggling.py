import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class H2CSmugglingDetection(NaslPlugin):
    PLUGIN_ID = 1206
    NAME = 'HTTP/2 Cleartext (H2C) Smuggling Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects H2C (HTTP/2 Cleartext) smuggling by sending an Upgrade: h2c header. If the server upgrades to HTTP/2, an attacker can smuggle HTTP/2 frames through the HTTP/1.1 proxy, bypassing security controls and WAF rules.'
    SOLUTION = 'Disable h2c upgrade on reverse proxies. Use strict HTTP/2 only on TLS. Configure proxy to reject Upgrade headers for non-standard protocols.'
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

                import base64
                settings = base64.b64encode(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00').decode()
                req = (
                    f'GET / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'Upgrade: h2c\r\n'
                    f'HTTP2-Settings: {settings}\r\n'
                    f'Connection: Upgrade, HTTP2-Settings\r\n'
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
                        if len(response) > 8192: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()
                if b'101' in response[:64] and (b'Switching Protocols' in response[:128] or b'h2c' in response.lower()):
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'H2C upgrade accepted on port {port_to_check}'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No H2C upgrade accepted'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
