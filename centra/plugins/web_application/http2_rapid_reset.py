import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class Http2RapidReset(NaslPlugin):
    PLUGIN_ID = 1246
    NAME = 'HTTP/2 Rapid Reset Attack Detection (CVE-2023-44487)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects vulnerability to HTTP/2 Rapid Reset (CVE-2023-44487) which allows attackers to send a stream of HTTP/2 requests followed immediately by resets, causing server-side resource exhaustion without the client completing requests. This was used in record-breaking DDoS attacks.'
    SOLUTION = 'Apply security patches for CVE-2023-44487 from your web server vendor. Set limits on HTTP/2 concurrent streams and stream reset rates. Use rate limiting on new connections.'
    CVE = ['CVE-2023-44487']
    PORTS = [443, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ctx.set_alpn_protocols(['h2', 'http/1.1'])
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                ssl_obj = writer.get_extra_info('ssl_object')
                negotiated = ssl_obj.selected_alpn_protocol()
                if negotiated == 'h2':
                    writer.close()
                    await writer.wait_closed()
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description='HTTP/2 supported via ALPN h2. Server may be vulnerable to CVE-2023-44487 Rapid Reset if unpatched.'))
                    continue
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                server_header = ''
                for line in response.split(b'\r\n'):
                    if line.lower().startswith(b'server:'):
                        server_header = line.split(b':', 1)[1].decode().strip()
                        break
                vulnerable_srv = any(v in server_header.lower() for v in ['nginx', 'apache', 'caddy', 'traefik', 'h2o', 'lighttpd', 'envoy', 'gunicorn'])
                if vulnerable_srv:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Server: {server_header}. Web server that may be vulnerable to CVE-2023-44487 if unpatched.'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'HTTP/2 not detected. Server: {server_header}'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
