import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class IframeSandboxCheck(NaslPlugin):
    PLUGIN_ID = 1191
    NAME = 'Iframe Sandbox Attribute Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Checks for missing or permissive sandbox attributes on iframes embedded in the target pages. Iframes without sandbox restrictions can execute scripts, submit forms, open popups, and navigate the parent page, enabling clickjacking and XSS attacks.'
    SOLUTION = 'Use restrictive sandbox attribute values (allow-scripts only if needed). Avoid allow-top-navigation, allow-popups, allow-same-origin unless absolutely necessary.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    DANGEROUS_TOKENS = ['allow-top-navigation', 'allow-popups', 'allow-same-origin', 'allow-pointer-lock', 'allow-orientation-lock']

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
                        iframe_pattern = re.compile(r'<iframe[^>]*>', re.IGNORECASE)
                        iframes = iframe_pattern.findall(html)
                        findings = []
                        for iframe in iframes:
                            has_sandbox = 'sandbox' in iframe.lower()
                            if not has_sandbox:
                                findings.append(f'Iframe missing sandbox attribute: {iframe[:100]}')
                            else:
                                sandbox_match = re.search(r'sandbox\s*=\s*["\']([^"\']*)["\']', iframe, re.IGNORECASE)
                                if sandbox_match:
                                    sandbox_val = sandbox_match.group(1).lower()
                                    for token in self.DANGEROUS_TOKENS:
                                        if token in sandbox_val:
                                            findings.append(f'Iframe has permissive sandbox token "{token}": {iframe[:100]}')
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'Iframe sandbox issues: {len(findings)} iframes',
                                solution=self.SOLUTION,
                                evidence='Iframe sandbox findings:\n' + '\n'.join(findings[:10])
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
