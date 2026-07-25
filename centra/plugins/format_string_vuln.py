"""
Plugin 1235: Python Format String Vulnerability Detection
===========================================================
Detects Python format string vulnerabilities where user input is passed
to str.format() or %-formatting.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class FormatStringVuln(NaslPlugin):
    PLUGIN_ID = 1235
    NAME = 'Python Format String Vulnerability Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects Python format string vulnerabilities where user input is passed '
        'to str.format() or %-formatting. Format string injection can leak '
        'sensitive variables, crash the application, or potentially execute code '
        'via class attribute traversal.'
    )
    SOLUTION = (
        'Do not use str.format() or % with user-controlled format strings. Use '
        'f-strings with fixed templates. Validate and sanitize all user input '
        'before using in format operations.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    FORMAT_PAYLOADS = [
        '{0.__class__.__init__.__globals__}',
        '%s%s%s%s%s%s%s%s',
        '{test.__class__}',
        '{0.__class__}',
        '{0.__class__.__bases__}',
        '{{}}',
    ]

    PARAMS = [
        'name', 'msg', 'message', 'format', 'template', 'input',
        'q', 'text', 'title', 'desc',
    ]

    PATHS = [
        '/', '/api', '/api/format', '/format', '/message',
        '/api/message', '/greet', '/hello',
    ]

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
                    for param in self.PARAMS[:5]:
                        for payload in self.FORMAT_PAYLOADS:
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                encoded = urllib.parse.quote(payload)
                                req = (
                                    f'GET {path}?{param}={encoded} HTTP/1.1\r\n'
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

                                body = response.split(b'\r\n\r\n', 1)
                                body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                                indicators = ['keyerror', 'indexerror', 'traceback', 'typeerror',
                                              'attributeerror', 'nameerror', 'syntaxerror',
                                              'class', 'globals', 'bases', '__init__',
                                              '__globals__', '__class__']
                                if any(ind in body_text.lower() for ind in indicators):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'Format string vulnerability detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, format string indicators found in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Format_string_attack',
                                        ]
                                    ))
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
                description='No format string vulnerability indicators detected on checked ports'
            ))

        return results
