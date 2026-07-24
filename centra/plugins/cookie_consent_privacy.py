"""
Plugin 1025: Cookie Consent & Privacy Compliance
==================================================
Checks for GDPR/CCPA/ePrivacy compliance indicators:
- Cookie consent banner/mechanism
- Privacy policy link
- Cookie policy link
- Data subject request mechanism
- "Do Not Sell" link (CCPA)
- Right to erasure mechanism
- Consent withdrawal mechanism

Real regulatory references:
- GDPR Art. 7 (Conditions for consent)
- GDPR Art. 12-14 (Transparency obligations)
- GDPR Art. 17 (Right to erasure)
- CCPA §1798.120 (Right to opt-out)
- ePrivacy Directive Art. 5(3) (Cookie consent)
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class CookieConsentPrivacy(NaslPlugin):
    PLUGIN_ID = 1025
    NAME = 'Cookie Consent & Privacy Compliance'
    FAMILY = 'Privacy & Compliance'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Checks for GDPR/CCPA/ePrivacy compliance indicators including cookie consent, '
        'privacy policy accessibility, data subject request mechanisms, and opt-out links.'
    )
    SOLUTION = (
        'Implement a cookie consent banner, publish a privacy policy, provide mechanisms '
        'for data subject requests (access, deletion, portability), and include opt-out links.'
    )
    PORTS = [80, 443]
    REFERENCES = [
        'https://gdpr-info.eu/art-7-gdpr/',
        'https://gdpr-info.eu/art-12-gdpr/',
        'https://gdpr-info.eu/art-17-gdpr/',
        'https://oag.ca.gov/privacy/ccpa',
    ]

    PRIVACY_POLICY_PATTERNS = [
        r'/privacy',
        r'/privacy-policy',
        r'/privacy\.html',
        r'/data-protection',
        r'/legal/privacy',
        r'privacy[_-]?policy',
    ]

    COOKIE_POLICY_PATTERNS = [
        r'/cookie',
        r'/cookie-policy',
        r'/cookies\.html',
        r'cookie[_-]?policy',
    ]

    CONSENT_BANNER_INDICATORS = [
        r'cookie[_-]?consent',
        r'cookie[_-]?banner',
        r'cookie[_-]?notice',
        r'consent[_-]?banner',
        r'consent[_-]?manager',
        r'cookiebot',
        r'onetrust',
        r'cookieyes',
        r'accept[_-]?cookies',
        r'cookie[_-]?preferences',
        r'manage[_-]?cookies',
        r'we[_-]?use[_-]?cookies',
        r'by[_-]?using[_-]?this[_-]?site',
    ]

    DO_NOT_SELL_PATTERNS = [
        r'do[_-]?not[_-]?sell',
        r'don\'?t[_-]?sell',
        r'opt[_-]?out',
        r'opt-out',
        r'your[_-]?privacy[_-]?choices',
        r'privacy[_-]?choices',
    ]

    DATA_SUBJECT_PATTERNS = [
        r'data[_\-\s]?subject',
        r'access[_\-\s]?request',
        r'access[_\-\s]?my[_\-\s]?data',
        r'delete[_\-\s]?my[_\-\s]?data',
        r'delete[_\-\s]?account',
        r'right[_\-\s]?to[_\-\s]?erasure',
        r'right[_\-\s]?to[_\-\s]?be[_\-\s]?forgotten',
        r'data[_\-\s]?portability',
        r'download[_\-\s]?my[_\-\s]?data',
        r'privacy[_\-\s]?request',
        r'gdpr[_\-\s]?request',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []

        try:
            scheme = 'https' if port == 443 else 'http'
            
            # Use SSL for HTTPS ports
            if port == 443:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ssl_context), timeout=10
                )
            else:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=10
                )

            req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=10)
                if not chunk:
                    break
                response += chunk
                if len(response) > 65536:
                    break

            writer.close()
            await writer.wait_closed()

            parts = response.split(b'\r\n\r\n', 1)
            body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
            body_lower = body.lower()

            issues = []
            passes = []

            has_privacy = False
            for pattern in self.PRIVACY_POLICY_PATTERNS:
                if re.search(pattern, body_lower):
                    has_privacy = True
                    passes.append('Privacy policy link found')
                    break

            if not has_privacy:
                issues.append('Missing privacy policy link (required by GDPR Art.12, CCPA)')

            has_cookie_policy = False
            for pattern in self.COOKIE_POLICY_PATTERNS:
                if re.search(pattern, body_lower):
                    has_cookie_policy = True
                    passes.append('Cookie policy link found')
                    break

            if not has_cookie_policy:
                issues.append('Missing cookie policy link (recommended for GDPR/ePrivacy)')

            has_consent = False
            for pattern in self.CONSENT_BANNER_INDICATORS:
                if re.search(pattern, body_lower):
                    has_consent = True
                    passes.append('Cookie consent mechanism detected')
                    break

            if not has_consent:
                issues.append('No cookie consent banner detected (required by ePrivacy Directive)')

            has_dns = False
            for pattern in self.DO_NOT_SELL_PATTERNS:
                if re.search(pattern, body_lower):
                    has_dns = True
                    passes.append('Do Not Sell / Opt-out link found')
                    break

            if not has_dns:
                issues.append('Missing "Do Not Sell" / opt-out link (required by CCPA §1798.120)')

            has_dsr = False
            for pattern in self.DATA_SUBJECT_PATTERNS:
                if re.search(pattern, body_lower):
                    has_dsr = True
                    passes.append('Data subject request mechanism detected')
                    break

            if not has_dsr:
                issues.append('No data subject request mechanism detected (GDPR Art.15-20)')

            if issues:
                severity = 'high' if len(issues) >= 3 else 'medium'
                evidence_lines = ['FAILURES:'] + [f'  - {i}' for i in issues]
                if passes:
                    evidence_lines.append('PASSES:')
                    evidence_lines += [f'  + {p}' for p in passes]

                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity=severity,
                    description=f'Privacy compliance gaps: {len(issues)} missing, {len(passes)} present',
                    solution=self.SOLUTION,
                    evidence='\n'.join(evidence_lines),
                    references=self.REFERENCES,
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False,
                    target=target,
                    port=port,
                    severity='info',
                    description='All privacy compliance checks passed',
                    evidence=f'Passed: {", ".join(passes)}',
                    references=self.REFERENCES,
                ))

        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check privacy compliance: {e}',
            ))

        return results
