import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class ContentTypeSniffingDetection(NaslPlugin):
    PLUGIN_ID = 1207
    NAME = 'MIME Type Sniffing Protection Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Checks for missing or permissive X-Content-Type-Options: nosniff header. Without this header, browsers may MIME-type sniff responses, potentially interpreting a user-uploaded image as HTML and enabling XSS.'
    SOLUTION = 'Set X-Content-Type-Options: nosniff on all responses. Serve user-uploaded content with proper Content-Type headers. Use Content-Disposition: attachment for untrusted files.'
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

                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk: break
                        response += chunk
                        if len(response) > 16384: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                if response:
                    header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else response
                    has_nosniff = b'X-Content-Type-Options: nosniff' in header_section or b'x-content-type-options: nosniff' in header_section.lower()
                    if has_nosniff:
                        results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='X-Content-Type-Options: nosniff is set'))
                    else:
                        results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description='Missing X-Content-Type-Options: nosniff header'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No response'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
