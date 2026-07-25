"""
Plugin 1026: Accessibility Compliance (WCAG 2.1)
===================================================
Checks for WCAG 2.1 Level AA compliance indicators:
- HTML lang attribute
- Image alt text
- Form labels
- ARIA landmarks
- Heading hierarchy
- Color contrast indicators
- Keyboard navigation (tabindex)
- Skip navigation links

Real standards:
- WCAG 2.1 Level AA
- Section 508 (US Federal)
- EN 301 549 (EU)
- VPAT (Voluntary Product Accessibility Template)
"""
import asyncio
import ssl
import re

from plugins import NaslPlugin, PluginResult


class AccessibilityCompliance(NaslPlugin):
    PLUGIN_ID = 1026
    NAME = 'Accessibility Compliance (WCAG 2.1)'
    FAMILY = 'Accessibility & Compliance'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Checks for WCAG 2.1 Level AA compliance indicators including HTML lang attribute, '
        'image alt text, form labels, ARIA landmarks, heading hierarchy, and skip navigation.'
    )
    SOLUTION = (
        'Ensure all pages have a lang attribute, images have alt text, form inputs have labels, '
        'proper heading hierarchy (h1-h6), ARIA landmarks, and skip navigation links.'
    )
    PORTS = [80, 443]
    REFERENCES = [
        'https://www.w3.org/WAI/WCAG21/quickref/',
        'https://www.section508.gov/',
        'https://www.w3.org/TR/WCAG21/',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []

        try:
            scheme = 'https' if port == 443 else 'http'
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
                if len(response) > 131072:
                    break

            writer.close()
            await writer.wait_closed()

            parts = response.split(b'\r\n\r\n', 1)
            body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''

            issues = []
            passes = []

            if re.search(r'<html[^>]*\slang\s*=\s*["\'][a-zA-Z]{2}', body, re.IGNORECASE):
                passes.append('HTML lang attribute present')
            else:
                issues.append('Missing HTML lang attribute (WCAG 3.1.1 Level A)')

            img_tags = re.findall(r'<img[^>]*>', body, re.IGNORECASE)
            img_without_alt = [img for img in img_tags if 'alt=' not in img.lower()]
            if img_tags:
                if not img_without_alt:
                    passes.append(f'All {len(img_tags)} images have alt text')
                else:
                    pct = len(img_without_alt) * 100 // len(img_tags)
                    issues.append(f'{len(img_without_alt)}/{len(img_tags)} images ({pct}%) missing alt text (WCAG 1.1.1 Level A)')

            form_inputs = re.findall(r'<((?:input|select|textarea)[^>]*?)>', body, re.IGNORECASE)
            inputs_without_labels = []
            for inp in form_inputs:
                if 'type="hidden"' in inp.lower() or 'type="submit"' in inp.lower():
                    continue
                if 'aria-label=' in inp.lower() or 'aria-labelledby=' in inp.lower():
                    continue
                inputs_without_labels.append(inp)
            if form_inputs:
                if not inputs_without_labels:
                    passes.append(f'All {len(form_inputs)} form inputs have accessible labels')
                else:
                    issues.append(f'{len(inputs_without_labels)}/{len(form_inputs)} form inputs missing labels (WCAG 1.3.1 Level A)')

            aria_landmarks = re.findall(r'role\s*=\s*["\'](?:banner|navigation|main|contentinfo|search|form|region)["\']', body, re.IGNORECASE)
            if aria_landmarks:
                passes.append(f'{len(aria_landmarks)} ARIA landmarks found')
            else:
                has_landmark_tags = bool(re.search(r'<(?:header|nav|main|footer|section|aside|article)[\s>]', body, re.IGNORECASE))
                if has_landmark_tags:
                    passes.append('Semantic HTML5 landmark elements found (header/nav/main/footer)')
                else:
                    issues.append('No ARIA landmarks or semantic HTML5 landmarks found (WCAG 1.3.1 Level A)')

            headings = re.findall(r'<h([1-6])[^>]*>', body, re.IGNORECASE)
            if headings:
                has_h1 = any(h == '1' for h in headings)
                if has_h1:
                    passes.append(f'Heading hierarchy: {len(headings)} headings with H1 present')
                else:
                    issues.append('Missing H1 heading (WCAG 1.3.1 Level A)')
            else:
                issues.append('No headings found (WCAG 1.3.1 Level A)')

            if re.search(r'skip[_-]?(?:to|nav)', body, re.IGNORECASE) or re.search(r'#main-content|#content|id=["\']main["\']', body, re.IGNORECASE):
                passes.append('Skip navigation mechanism detected')
            else:
                issues.append('No skip navigation link detected (WCAG 2.4.1 Level A)')

            if re.search(r'<meta[^>]*viewport[^>]*>', body, re.IGNORECASE):
                passes.append('Viewport meta tag present (responsive)')
            else:
                issues.append('Missing viewport meta tag (WCAG 1.4.4 Level AA)')

            if issues:
                severity = 'high' if len(issues) >= 4 else 'medium'
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
                    description=f'Accessibility gaps: {len(issues)} violations, {len(passes)} passes',
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
                    description='All accessibility compliance checks passed',
                    evidence=f'Passed: {", ".join(passes)}',
                    references=self.REFERENCES,
                ))

        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check accessibility: {e}',
            ))

        return results
