"""
Plugin 1226: Expression Language (EL) Injection Detection
===========================================================
Detects Expression Language (EL) injection vulnerabilities by injecting
EL expressions like ${7*7}, #{7*7}, and %d{7*7} into parameters.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class ElInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1226
    NAME = 'Expression Language (EL) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Expression Language (EL) injection vulnerabilities by injecting '
        'EL expressions like ${7*7}, #{7*7}, and %d{7*7} into parameters. '
        'EL injection is common in Java-based applications and can lead to full RCE.'
    )
    SOLUTION = (
        'Avoid evaluating user input as EL expressions. Sanitize and validate all '
        'user input. Use a sandboxed EL evaluator. Keep EL libraries updated.'
    )
    CVE = ['CVE-2021-29441', 'CVE-2022-22965']
    PORTS = [80, 443, 8080, 8443]

    EL_PAYLOADS = [
        '${7*7}',
        '#{7*7}',
        '%d{7*7}',
        '${request.getParameter("test")}',
    ]

    PARAMS = [
        'name', 'id', 'user', 'username', 'search', 'q', 'input',
    ]

    PATHS = ['/', '/api', '/login', '/search']

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
                        for payload in self.EL_PAYLOADS:
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

                                if '49' in body_text and '${7*7}' in payload:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'EL injection detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, expression evaluated (7*7=49)',
                                        references=[
                                            'https://owasp.org/www-community/attacks/EL_Injection',
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
                description='No EL injection indicators detected on checked ports'
            ))

        return results
