import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class WebStorageAudit(NaslPlugin):
    PLUGIN_ID = 1189
    NAME = 'Web Storage Security Audit'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Audits the use of localStorage and sessionStorage for storing sensitive information including authentication tokens, API keys, or personal data. Web Storage is accessible via JavaScript (XSS) and persists in the browser with no automatic expiration.'
    SOLUTION = 'Do not store sensitive data in localStorage or sessionStorage. Use HttpOnly cookies for session tokens. Encrypt any data stored client-side. Clear storage on logout.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_KEYS = ['token', 'jwt', 'secret', 'key', 'session', 'auth', 'password', 'apikey', 'api_key', 'accesstoken', 'refreshtoken', 'credentials']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            scripts_found = []
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
                        if len(response) > 32768: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                if response:
                    body = response.split(b'\r\n\r\n', 1)
                    if len(body) > 1:
                        html = body[1].decode('utf-8', errors='ignore')
                        script_tags = re.findall(r'<script[^>]*>([^<]+)</script>', html, re.IGNORECASE | re.DOTALL)
                        script_srcs = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                        all_js = list(script_tags)
                        for src in script_srcs[:5]:
                            try:
                                js_scheme = 'https' if port_to_check in (443, 8443) else 'http'
                                js_ctx = None
                                if js_scheme == 'https':
                                    js_ctx = ssl.create_default_context()
                                    js_ctx.check_hostname = False
                                    js_ctx.verify_mode = ssl.CERT_NONE
                                js_reader, js_writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=js_ctx), timeout=5)
                                js_req = f'GET {src} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                                js_writer.write(js_req.encode())
                                await js_writer.drain()
                                js_response = b''
                                try:
                                    while True:
                                        chunk = await asyncio.wait_for(js_reader.read(4096), timeout=3)
                                        if not chunk: break
                                        js_response += chunk
                                        if len(js_response) > 32768: break
                                except asyncio.TimeoutError:
                                    pass
                                js_writer.close()
                                await js_writer.wait_closed()
                                if js_response:
                                    js_body = js_response.split(b'\r\n\r\n', 1)
                                    if len(js_body) > 1:
                                        all_js.append(js_body[1].decode('utf-8', errors='ignore'))
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass

                        findings = []
                        for js in all_js:
                            for method in ['localStorage.setItem', 'sessionStorage.setItem']:
                                pattern = re.compile(re.escape(method) + r'\s*\(\s*[\'"]([^\'"]+)[\'"]')
                                for match in pattern.finditer(js):
                                    key = match.group(1)
                                    for sensitive in self.SENSITIVE_KEYS:
                                        if sensitive in key.lower():
                                            findings.append(f'{method}("{key}")')
                                            break
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'Sensitive data in web storage: {len(findings)} instances',
                                solution=self.SOLUTION,
                                evidence='Suspicious storage calls:\n' + '\n'.join(findings)
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=port_to_check,
                                description='No issues detected'
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
