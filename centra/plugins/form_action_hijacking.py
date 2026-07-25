import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class FormActionHijacking(NaslPlugin):
    PLUGIN_ID = 1194
    NAME = 'Form Action Hijacking Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects forms with missing or relative action attributes that are susceptible to form action hijacking via injected base tags or DOM manipulation. If a form submits to a relative URL, an attacker who can inject a <base> tag can redirect form submissions.'
    SOLUTION = 'Always use absolute URLs in form action attributes. Validate form action on the server side. Use CSP base-uri directive to restrict <base> tags.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                    body = response.split(b'\r\n\r\n', 1)
                    if len(body) > 1:
                        html = body[1].decode('utf-8', errors='ignore')
                        form_pattern = re.compile(r'<form[^>]*>', re.IGNORECASE)
                        forms = form_pattern.findall(html)
                        findings = []
                        for form_tag in forms:
                            action_match = re.search(r'action\s*=\s*["\']([^"\']*)["\']', form_tag, re.IGNORECASE)
                            if action_match:
                                action_val = action_match.group(1)
                                if action_val and not action_val.startswith('http://') and not action_val.startswith('https://') and not action_val.startswith('//'):
                                    if action_val.startswith('/') or action_val.startswith('.'):
                                        findings.append(f'Relative form action: action="{action_val}"')
                            else:
                                findings.append(f'Form missing action attribute: {form_tag[:80]}')
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'Form action hijacking risks: {len(findings)} form(s) with relative/missing action',
                                solution=self.SOLUTION,
                                evidence='Form action issues:\n' + '\n'.join(findings[:10])
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=port_to_check,
                                description='No issues detected'
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
