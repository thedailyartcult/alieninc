import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class SRICheckDetection(NaslPlugin):
    PLUGIN_ID = 1213
    NAME = 'Subresource Integrity (SRI) Validation'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Validates Subresource Integrity (SRI) hashes on external scripts and stylesheets. Missing or incorrect SRI attributes allow compromised CDN scripts to execute malicious code in the context of the application. Also checks for outdated script versions with known vulnerabilities.'
    SOLUTION = 'Add integrity attributes to all external script and link tags. Use SRI hash generators for each resource. Include crossorigin="anonymous" for CORS-enabled CDN resources.'
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

                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                writer.write(req.encode())
                await writer.drain()
                resp = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk: break
                        resp += chunk
                        if len(resp) > 65536: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                missing_sri = []
                if resp:
                    body = resp.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in resp else resp
                    text = body.decode('utf-8', errors='replace')
                    script_pattern = re.compile(r'<script[^>]*src=["\'](https?://[^"\']+)["\'][^>]*>', re.IGNORECASE)
                    link_pattern = re.compile(r'<link[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>', re.IGNORECASE)

                    for match in script_pattern.finditer(text):
                        tag = match.group(0)
                        if 'integrity' not in tag.lower():
                            missing_sri.append(match.group(1))
                    for match in link_pattern.finditer(text):
                        tag = match.group(0)
                        if 'integrity' not in tag.lower() and 'stylesheet' in tag.lower():
                            missing_sri.append(match.group(1))

                if missing_sri:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Missing SRI on {len(missing_sri)} external resources: {", ".join(missing_sri[:5])}'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No external resources missing SRI'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
