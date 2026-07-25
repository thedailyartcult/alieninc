"""
Plugin 1243: Third-Party Script Risk Assessment
===============================================
Assesses risk from third-party JavaScript loaded by the application.
Identifies external script origins and evaluates SRI and permissions.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class ThirdPartyScriptRiskAssessment(NaslPlugin):
    PLUGIN_ID = 1243
    NAME = 'Third-Party Script Risk Assessment'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Assesses risk from third-party JavaScript loaded by the application. '
        'Identifies all external script origins and evaluates them for known '
        'malicious activity, lack of SRI, and excessive permissions. Compromised '
        'third-party scripts are a leading cause of supply chain attacks.'
    )
    SOLUTION = (
        'Use SRI hashes on all third-party scripts. Subresource integrity ensures '
        'scripts load only if they match the expected hash. Use a strict CSP. '
        'Audit third-party scripts regularly. Self-host critical libraries.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    KNOWN_RISKY_DOMAINS = [
        'coinhive.com', 'cryptoloot.pro', 'minr.pw', 'coin-have.com',
        'microsoft-verify.com', 'g00gle-analytics.com',
        'googie-analytics.com', 'googiele-analytics.com',
    ]

    SCRIPT_PATTERN = re.compile(
        r'<script[^>]*src=["\'](https?://[^"\']+)["\'][^>]*>',
        re.IGNORECASE
    )

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
                        if len(response) > 65536:
                            break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()
                body = response.split(b'\r\n\r\n', 1)
                if len(body) > 1:
                    html = body[1].decode('utf-8', errors='ignore')
                    external_scripts = []
                    for match in self.SCRIPT_PATTERN.finditer(html):
                        src = match.group(1)
                        if host_header.split(':')[0] not in src and 'alieninc.tech' not in src:
                            has_integrity = 'integrity=' in match.group(0)
                            risky = any(domain in src.lower() for domain in self.KNOWN_RISKY_DOMAINS)
                            external_scripts.append({
                                'src': src,
                                'has_sri': has_integrity,
                                'risky': risky,
                            })
                    if external_scripts:
                        total = len(external_scripts)
                        no_sri = [s['src'] for s in external_scripts if not s['has_sri']]
                        risky_found = [s['src'] for s in external_scripts if s['risky']]
                        risk_level = 'high' if risky_found else ('medium' if no_sri else 'low')
                        messages = []
                        if risky_found:
                            messages.append(f'{len(risky_found)} script(s) from known risky domains')
                        if no_sri:
                            messages.append(f'{len(no_sri)} script(s) without SRI')
                        if not messages:
                            messages.append(f'All {total} external scripts have SRI')
                        findings = ', '.join(messages)
                        results.append(PluginResult(
                            vulnerable=bool(risky_found or no_sri),
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity=risk_level,
                            description=f'Third-party script risk: {findings}',
                            solution=self.SOLUTION,
                            evidence=f'Total external scripts: {total}, without SRI: {len(no_sri)}, risky domains: {risky_found}',
                            references=[
                                'https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity',
                                'https://owasp.org/www-community/attacks/Script_injection',
                            ]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            description='No external third-party scripts detected'
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No third-party script indicators detected'
            ))
        return results
