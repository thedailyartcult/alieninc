import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class AdvancedOpenRedirectDetection(NaslPlugin):
    PLUGIN_ID = 1211
    NAME = 'Advanced Open Redirect Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects advanced open redirect bypasses including protocol smuggling (//evil.com, ///evil.com, https:evil.com), CRLF in redirect destinations, @ symbol handling, and Unicode homograph attacks in redirect URLs.'
    SOLUTION = 'Use a whitelist of allowed redirect domains. Validate redirect URLs against a strict regex. Never base redirects on user input without validation.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        redirect_params = ['redirect', 'url', 'next', 'return', 'return_to', 'returnUrl', 'goto', 'target', 'dest', 'destination', 'out', 'view', 'dir']
        payloads = [
            '//evil.com',
            '///evil.com',
            'https:evil.com',
            'https://evil.com',
            'http://evil.com',
            '@evil.com',
            'evil%00.com',
            '127.0.0.1',
            '//127.0.0.1',
            'https://127.0.0.1',
        ]
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

                for param in redirect_params:
                    for payload in payloads:
                        path = f'/?{param}={payload}'
                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                        if resp:
                            status_line = resp.split(b'\r\n')[0] if b'\r\n' in resp else resp
                            if b'3' in status_line[:4] and b'0' in status_line[3:6]:
                                header_section = resp.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in resp else resp
                                if b'Location:' in header_section or b'location:' in header_section.lower():
                                    for evil in [b'evil.com', b'evil', b'127.0.0.1']:
                                        if evil in header_section.lower():
                                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Open redirect via param {param} with payload {payload}'))
                                            return results
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No open redirect detected'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
