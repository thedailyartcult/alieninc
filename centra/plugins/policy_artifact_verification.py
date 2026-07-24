"""
Plugin 1031: Policy & Compliance Artifact Verification
=======================================================
Checks that organizational and policy artifacts exist, are accessible,
and contain required content. These artifacts are required by multiple
compliance frameworks as evidence of transparency and accountability.

Checks:
  - /.well-known/security.txt (RFC 9116) — vulnerability disclosure contact
  - /robots.txt — proper blocking of sensitive paths
  - /pgp-key.txt — responsible disclosure encryption key
  - /privacy.html — privacy policy accessibility and content
  - /cookies.html — cookie policy accessibility and content
  - /compliance.html — compliance statement accessibility
  - /terms.html — terms of service accessibility
  - Cookie consent mechanism on main page
  - Data subject request links (GDPR Art.15-20, CCPA)
  - Accessibility statement (VPAT/WCAG)

Real references:
  - RFC 9116 — A File Format to Aid in Security Vulnerability Disclosure
  - GDPR Art.12-14 — Transparency obligations
  - GDPR Art.33 — Breach notification
  - CCPA §1798.110 — Notice at collection
  - ISO 27001 A.5.34 — Privacy and PII protection
  - ISO 27001 A.5.37 — Documented operating procedures
  - SOC 2 CC7.3 — Incident response procedures
  - FedRAMP IR-6 — Incident reporting
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class PolicyArtifactVerification(NaslPlugin):
    PLUGIN_ID = 1031
    NAME = 'Policy & Compliance Artifact Verification'
    FAMILY = 'Compliance & Governance'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Verifies that organizational policy artifacts exist and are properly '
        'configured: security.txt (RFC 9116), robots.txt, PGP key, privacy policy, '
        'cookie policy, compliance statement, terms of service, cookie consent, '
        'and data subject request mechanisms.'
    )
    SOLUTION = (
        'Ensure all required policy artifacts are published and accessible. '
        'security.txt must follow RFC 9116 format. Privacy and cookie policies '
        'must be accessible from every page. PGP key must be published for '
        'responsible disclosure.'
    )
    PORTS = [80, 443]
    PLUGIN_TYPE = 'remote'

    REQUIRED_ARTIFACTS = {
        '/.well-known/security.txt': {
            'name': 'Security.txt (RFC 9116)',
            'required_fields': ['Contact', 'Expires'],
            'framework': 'SOC 2 CC7.3, FedRAMP IR-6, ISO 27001 A.5.37',
        },
        '/robots.txt': {
            'name': 'robots.txt',
            'required_content': ['User-agent', 'Disallow'],
            'framework': 'SOC 2 CC6.6, ISO 27001 A.8.9',
        },
        '/pgp-key.txt': {
            'name': 'PGP Key (Responsible Disclosure)',
            'required_content': ['BEGIN PGP'],
            'framework': 'SOC 2 CC7.3, ISO 27001 A.5.37',
        },
        '/privacy.html': {
            'name': 'Privacy Policy',
            'required_content': ['privacy', 'data', 'collect'],
            'framework': 'GDPR Art.12-14, CCPA §1798.110, ISO 27001 A.5.34',
        },
        '/cookies.html': {
            'name': 'Cookie Policy',
            'required_content': ['cookie'],
            'framework': 'GDPR Art.5, ePrivacy Directive',
        },
        '/compliance.html': {
            'name': 'Compliance Statement',
            'required_content': ['compliance', 'audit'],
            'framework': 'SOC 2, ISO 27001, FedRAMP',
        },
        '/terms.html': {
            'name': 'Terms of Service',
            'required_content': ['terms'],
            'framework': 'SOC 2 CC6.1, CCPA',
        },
    }

    DATA_SUBJECT_LINKS = [
        r'access[_\-\s]?my[_\-\s]?data',
        r'delete[_\-\s]?my[_\-\s]?data',
        r'data[_\-\s]?request',
        r'data[_\-\s]?subject',
        r'right[_\-\s]?to[_\-\s]?erasure',
        r'your[_\-\s]?privacy[_\-\s]?choices',
    ]

    CONSENT_INDICATORS = [
        r'cookie[_\-\s]?consent',
        r'accept[_\-\s]?cookies',
        r'we[_\-\s]?use[_\-\s]?cookies',
        r'cookie[_\-\s]?banner',
        r'manage[_\-\s]?cookies',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []
        host_header = target
        if target in ('127.0.0.1', 'localhost', '::1'):
            host_header = 'alieninc.tech'

        issues = []
        passes = []

        for path, config in self.REQUIRED_ARTIFACTS.items():
            status, headers, body = await self._fetch(target, port, path, host_header)

            if '200' not in status:
                issues.append(f'MISSING: {config["name"]} ({path}) — returned {status.split(chr(13))[0]} [{config["framework"]}]')
                continue

            missing_content = []
            for required in config.get('required_content', []):
                if required.lower() not in body.lower():
                    missing_content.append(required)
            for required in config.get('required_fields', []):
                if not re.search(rf'^{required}\s*:', body, re.IGNORECASE | re.MULTILINE):
                    missing_content.append(required)

            if missing_content:
                issues.append(f'INCOMPLETE: {config["name"]} — missing: {", ".join(missing_content)} [{config["framework"]}]')
            else:
                passes.append(f'OK: {config["name"]} [{config["framework"]}]')

        status, headers, body = await self._fetch(target, port, '/', host_header)
        body_lower = body.lower()

        has_consent = any(re.search(p, body_lower) for p in self.CONSENT_INDICATORS)
        if has_consent:
            passes.append('OK: Cookie consent mechanism detected [GDPR Art.7, ePrivacy]')
        else:
            issues.append('MISSING: Cookie consent mechanism [GDPR Art.7, ePrivacy Directive]')

        has_dsr = any(re.search(p, body_lower) for p in self.DATA_SUBJECT_LINKS)
        if has_dsr:
            passes.append('OK: Data subject request links found [GDPR Art.15-20, CCPA §1798.120]')
        else:
            issues.append('MISSING: Data subject request links [GDPR Art.15-20, CCPA §1798.120]')

        has_lang = bool(re.search(r'<html[^>]*\slang\s*=', body, re.IGNORECASE))
        has_skip = bool(re.search(r'skip[_\-\s]?(?:to|nav)|#main[-_]?content', body, re.IGNORECASE))
        has_aria = bool(re.search(r'role\s*=\s*["\'](?:banner|navigation|main|contentinfo)', body, re.IGNORECASE))

        a11y_checks = []
        if has_lang:
            a11y_checks.append('lang')
        if has_skip:
            a11y_checks.append('skip-nav')
        if has_aria:
            a11y_checks.append('aria-landmarks')

        if len(a11y_checks) >= 2:
            passes.append(f'OK: Accessibility markers ({", ".join(a11y_checks)}) [VPAT/WCAG 2.1 AA]')
        else:
            issues.append(f'INCOMPLETE: Accessibility markers — only: {", ".join(a11y_checks) if a11y_checks else "none"} [VPAT/WCAG 2.1 AA]')

        if issues:
            evidence_lines = ['FAILURES:'] + [f'  - {i}' for i in issues]
            if passes:
                evidence_lines.append('PASSES:')
                evidence_lines += [f'  + {p}' for p in passes]

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='medium',
                description=f'Policy verification: {len(issues)} issues, {len(passes)} passes',
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=self.REFERENCES if hasattr(self, 'REFERENCES') else [],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'All policy artifacts verified: {len(passes)} checks passed',
                evidence='PASSES: ' + '; '.join(passes),
                references=self.REFERENCES if hasattr(self, 'REFERENCES') else [],
            ))

        return results

    async def _fetch(self, target, port, path, host_header, timeout=8):
        try:
            if port == 443:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ssl_ctx), timeout=timeout
                )
            else:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=timeout
                )
        except Exception:
            return ('ERROR', {}, '')

        try:
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n'
                f'\r\n'
            )
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                if not chunk:
                    break
                response += chunk
                if len(response) > 65536:
                    break

            writer.close()
            await writer.wait_closed()

            parts = response.split(b'\r\n\r\n', 1)
            header_section = parts[0].decode('utf-8', errors='ignore')
            body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''

            headers = {}
            lines = header_section.split('\r\n')
            status = lines[0] if lines else ''
            for line in lines[1:]:
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip().lower()] = v.strip()

            return (status, headers, body)
        except Exception:
            return ('TIMEOUT', {}, '')
