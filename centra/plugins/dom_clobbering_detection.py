"""
Plugin 1236: DOM Clobbering Detection
======================================
Detects DOM clobbering vulnerabilities where HTML elements with id or
name attributes override global JavaScript variables.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class DomClobberingDetection(NaslPlugin):
    PLUGIN_ID = 1236
    NAME = 'DOM Clobbering Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Detects DOM clobbering vulnerabilities where HTML elements with id or '
        'name attributes override global JavaScript variables. Tests by injecting '
        'anchor elements with id attributes to see if they clobber window or '
        'document properties. DOM clobbering can bypass XSS filters and hijack '
        'application logic.'
    )
    SOLUTION = (
        'Use Object.create(null) for safe dictionaries. Avoid relying on global '
        'variable access for security decisions. Use let/const and block scoping. '
        'Sanitize HTML to remove id/name collisions with built-in properties.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    CLONBER_PATTERNS = [
        'id="xss"',
        'name="xss"',
        '<a id="',
        'id="defaultView"',
        'id="body"',
        'id="location"',
        'id="cookie"',
    ]

    INJECTION_PARAMS = ['q', 'search', 'query', 's', 'text', 'input', 'page', 'id']

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
                probe_payload = '<a id="xss" href="https://evil.com">'
                for param in self.INJECTION_PARAMS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        encoded = probe_payload.replace(' ', '%20').replace('<', '%3C').replace('>', '%3E').replace('"', '%22')
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
                            for pat in self.CLONBER_PATTERNS:
                                if pat in text:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='medium',
                                        description=(
                                            f'DOM clobbering vector detected via param "{param}" '
                                            f'- pattern "{pat}" reflected in response'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Injected: {probe_payload}, reflected pattern: {pat}',
                                        references=[
                                            'https://portswigger.net/web-security/dom-clobbering',
                                            'https://owasp.org/www-community/attacks/DOM_Clobbering',
                                        ]
                                    ))
                                    break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                    if results:
                        break
                if not results:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                    )
                    req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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
                        id_attribs = text.count('id="')
                        if id_attribs > 50:
                            results.append(PluginResult(
                                vulnerable=False,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='info',
                                description=(
                                    f'Page has {id_attribs} id attributes - potential DOM clobbering surface area'
                                ),
                                solution=self.SOLUTION,
                                evidence=f'{id_attribs} id attributes found on page',
                                references=[
                                    'https://portswigger.net/web-security/dom-clobbering',
                                ]
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No DOM clobbering indicators detected'
            ))
        return results
