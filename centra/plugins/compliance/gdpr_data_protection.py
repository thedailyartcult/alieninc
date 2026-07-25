"""
Plugin 1161: GDPR Data Protection Controls Check
==================================================
Checks for basic GDPR data protection indicators including privacy policy
presence, cookie consent mechanisms, and data minimization signals.
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class GdprDataProtection(NaslPlugin):
    PLUGIN_ID = 1161
    NAME = 'GDPR Data Protection Controls Check'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Checks for basic GDPR data protection indicators including privacy '
        'policy presence, cookie consent mechanisms, and data minimization '
        'signals. While not definitive, these indicators suggest GDPR compliance '
        'posture.'
    )
    SOLUTION = (
        'Implement cookie consent management. Publish privacy policy. Implement '
        'data minimization and purpose limitation. Provide data access and '
        'deletion mechanisms.'
    )
    PORTS = [80, 443, 8080, 8443]

    PRIVACY_PATTERNS = [
        r'privacy[\s_-]*policy',
        r'privacy[\s_-]*notice',
        r'data[\s_-]*protection',
        r'gdpr',
        r'cookie[\s_-]*policy',
        r'cookie[\s_-]*consent',
        r'cookies?(\s|$)',
    ]
    CONSENT_PATTERNS = [
        r'cookie[\s_-]*consent',
        r'cookie[\s_-]*notice',
        r'cookie[\s_-]*banner',
        r'cookie[\s_-]*bar',
        r'accept[\s_-]*cookies',
        r'reject[\s_-]*cookies',
        r'cookie[\s_-]*settings',
        r'consent[\s_-]*manager',
    ]
    DATA_MINIMIZATION = [
        r'data[\s_-]*minimi[sz]ation',
        r'purpose[\s_-]*limitation',
        r'data[\s_-]*retention',
        r'personal[\s_-]*data',
        r'subject[\s_-]*access',
        r'right[\s_-]*to[\s_-]*access',
        r'right[\s_-]*to[\s_-]*be[\s_-]*forgotten',
        r'data[\s_-]*deletion',
        r'data[\s_-]*portability',
        r'breach[\s_-]*notification',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check), timeout=5
                )
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 32768:
                        break
                writer.close()
                await writer.wait_closed()

                body = response.split(b'\r\n\r\n', 1)
                body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''
                body_lower = body_text.lower()

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                headers = {}
                for line in header_section.split('\r\n')[1:]:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        headers[key.strip().lower()] = val.strip()

                privacy_found = bool(re.search('|'.join(self.PRIVACY_PATTERNS), body_lower))
                consent_found = bool(re.search('|'.join(self.CONSENT_PATTERNS), body_lower))
                data_min_found = bool(re.search('|'.join(self.DATA_MINIMIZATION), body_lower))

                missing = []
                if not privacy_found:
                    missing.append('Privacy policy not detected')
                if not consent_found:
                    missing.append('Cookie consent mechanism not detected')
                if not data_min_found:
                    missing.append('Data minimization/purpose signals not detected')

                if missing:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'GDPR data protection indicators missing: {"; ".join(missing)}',
                        solution=self.SOLUTION,
                        evidence=f'Privacy: {privacy_found}, Consent: {consent_found}, DataMin: {data_min_found}',
                        references=[
                            'https://gdpr-info.eu/',
                            'https://www.tenable.com/plugins/nessus/70782',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='Basic GDPR data protection indicators present',
                        evidence=f'Privacy policy, cookie consent, and data minimization signals detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
