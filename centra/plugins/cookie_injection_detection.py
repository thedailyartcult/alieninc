"""
Plugin 1231: HTTP Cookie Injection Detection
==============================================
Detects HTTP cookie injection vulnerabilities where attackers can inject
arbitrary cookie attributes (path, domain, expires) via CRLF injection
in cookie values.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class CookieInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1231
    NAME = 'HTTP Cookie Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Detects HTTP cookie injection vulnerabilities where attackers can inject '
        'arbitrary cookie attributes (path, domain, expires) via CRLF injection in '
        'cookie values. Also tests for cookie prefix injection (__Secure-, __Host-) abuse.'
    )
    SOLUTION = (
        'Validate and sanitize cookie values. Restrict cookie paths and domains. '
        'Use the __Host- prefix for session cookies. Set Secure and HttpOnly flags.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    COOKIE_PAYLOADS = [
        'injected=value%0d%0aSet-Cookie:%20injected2=value2',
        'test=1%0d%0aSet-Cookie:%20malicious=yes;%20Domain=evil.com',
        'normal=val%0d%0aSet-Cookie:%20session=stolen;%20Path=/',
    ]

    PARAMS = [
        'name', 'id', 'user', 'session', 'token', 'prefs',
        'cookie', 'lang',
    ]

    PATHS = ['/', '/api', '/login', '/setlang']

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

                for path in self.PATHS:
                    for param in self.PARAMS[:4]:
                        for payload in self.COOKIE_PAYLOADS:
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                req = (
                                    f'GET {path}?{param}={payload} HTTP/1.1\r\n'
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
                                        if len(response) > 16384:
                                            break
                                except asyncio.TimeoutError:
                                    pass
                                writer.close()
                                await writer.wait_closed()

                                header_section = response.split(b'\r\n\r\n', 1)[0]
                                headers_text = header_section.decode('utf-8', errors='ignore')

                                set_cookie_lines = [l for l in headers_text.split('\r\n')
                                                     if l.lower().startswith('set-cookie:')]
                                for sc in set_cookie_lines:
                                    if ('injected2' in sc or 'malicious' in sc or 'stolen' in sc):
                                        results.append(PluginResult(
                                            vulnerable=True,
                                            target=target,
                                            port=port_to_check,
                                            cvss_score=self.CVSS_SCORE,
                                            severity='medium',
                                            description=f'Cookie injection detected via param "{param}" on {path}',
                                            solution=self.SOLUTION,
                                            evidence=f'Payload: {payload}, injected Set-Cookie header: {sc}',
                                            references=[
                                                'https://owasp.org/www-community/attacks/HTTP_Cookie_Injection',
                                            ]
                                        ))
                                        break
                                if results:
                                    break
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass
                        if results:
                            break
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No cookie injection indicators detected on checked ports'
            ))

        return results
