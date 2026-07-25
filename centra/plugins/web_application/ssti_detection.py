"""
Plugin 1116: Server-Side Template Injection Detection
======================================================
Detects SSTI vulnerabilities by injecting template syntax probes
into common parameters. Tests for Jinja2, Twig, Smarty, Mako,
and FreeMarker template engines.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class SstiDetection(NaslPlugin):
    PLUGIN_ID = 1116
    NAME = 'Server-Side Template Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Server-Side Template Injection (SSTI) vulnerabilities by '
        'injecting template syntax probes ({{7*7}}, {{7*\'7\'}}, ${7*7}) into '
        'common parameters. SSTI can lead to full RCE on the target server. '
        'Tests for Jinja2, Twig, Smarty, Mako, and FreeMarker template engines.'
    )
    SOLUTION = (
        'Avoid rendering user input in template expressions. Use sandboxed '
        'template engines. Validate and sanitize all user input.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SSTI_PAYLOADS = [
        ('{{7*7}}', '49'),
        ('{{7*\'7\'}}', '7777777'),
        ('${7*7}', '49'),
        ('#{7*7}', '49'),
        ('*{7*7}', '49'),
        ('{{config}}', 'config'),
    ]

    PARAMS = [
        'name', 'q', 'search', 'query', 'page', 'template', 'view',
        'input', 'first_name', 'last_name', 'username', 'email',
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

                for payload, indicator in self.SSTI_PAYLOADS:
                    for param in self.PARAMS[:5]:
                        encoded = urllib.parse.quote(payload)
                        query = f'{param}={encoded}'

                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )

                        for path in ['/', '/search', '/api/search']:
                            req = (
                                f'GET {path}?{query} HTTP/1.1\r\n'
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

                            body = response.split(b'\r\n\r\n', 1)
                            body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                            if indicator in body_text:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'SSTI indicator detected with payload "{payload}" on {path}',
                                    solution=self.SOLUTION,
                                    evidence=f'Payload: {payload}, indicator: "{indicator}" found in response body',
                                    references=[
                                        'https://portswigger.net/web-security/server-side-template-injection',
                                        'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/18-Testing_for_Server_Side_Template_Injection',
                                    ]
                                ))
                                break

                        writer.close()
                        await writer.wait_closed()

                        if results:
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No SSTI indicators detected on checked ports'
            ))

        return results
