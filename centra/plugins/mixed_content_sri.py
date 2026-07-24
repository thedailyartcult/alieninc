"""
Plugin 1029: Mixed Content & Subresource Integrity (SRI)
==========================================================
Checks for mixed content (HTTP resources on HTTPS pages) and
Subresource Integrity (SRI) on external scripts/stylesheets.

Real standards:
- SOC 2 CC6.2 (Encryption in transit)
- ISO 27001 A.8.24 (Use of cryptography)
- NIST 800-53 SC-8 (Transmission confidentiality)
- PCI DSS 4.1 (Strong cryptography for transmission)
"""
import asyncio
import ssl
import re

from plugins import NaslPlugin, PluginResult


class MixedContentSRI(NaslPlugin):
    PLUGIN_ID = 1029
    NAME = 'Mixed Content & Subresource Integrity'
    FAMILY = 'Web Security'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 4.3
    DESCRIPTION = (
        'Checks for mixed content (HTTP resources on HTTPS pages) and missing '
        'Subresource Integrity (SRI) on external scripts/stylesheets.'
    )
    SOLUTION = (
        'Serve all resources over HTTPS. Add integrity and crossorigin attributes to '
        'external script and link tags. Use protocol-relative URLs or absolute HTTPS URLs.'
    )
    PORTS = [80, 443]
    REFERENCES = [
        'https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content',
        'https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []

        if port != 443:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description='Mixed content check only applies to HTTPS',
            ))
            return results

        try:
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

            http_script_pattern = re.compile(r'<script[^>]+src=["\']http://[^"\']+["\']', re.IGNORECASE)
            http_link_pattern = re.compile(r'<link[^>]+href=["\']http://[^"\']+["\']', re.IGNORECASE)
            http_img_pattern = re.compile(r'<img[^>]+src=["\']http://[^"\']+["\']', re.IGNORECASE)

            http_scripts = http_script_pattern.findall(body)
            http_links = http_link_pattern.findall(body)
            http_imgs = http_img_pattern.findall(body)

            if http_scripts:
                issues.append(f'{len(http_scripts)} script(s) loaded over HTTP (mixed content)')
            if http_links:
                issues.append(f'{len(http_links)} stylesheet(s) loaded over HTTP (mixed content)')
            if http_imgs:
                issues.append(f'{len(http_imgs)} image(s) loaded over HTTP (mixed content)')

            if not http_scripts and not http_links and not http_imgs:
                passes.append('No mixed content detected (all resources over HTTPS)')

            external_scripts = re.findall(r'<script[^>]+src=["\']https?://[^"\']+["\']', body, re.IGNORECASE)
            external_scripts += re.findall(r'<script[^>]+src=["\']//[^"\']+["\']', body, re.IGNORECASE)

            scripts_without_sri = []
            for script in external_scripts:
                if 'http://' in script.lower():
                    continue
                if 'integrity=' not in script.lower():
                    scripts_without_sri.append(script)

            external_links = re.findall(r'<link[^>]+href=["\']https?://[^"\']+["\']', body, re.IGNORECASE)
            external_links += re.findall(r'<link[^>]+href=["\']//[^"\']+["\']', body, re.IGNORECASE)

            links_without_sri = []
            for link in external_links:
                if 'http://' in link.lower():
                    continue
                if 'rel="stylesheet"' in link.lower() and 'integrity=' not in link.lower():
                    links_without_sri.append(link)

            total_external = len(external_scripts) + len([l for l in external_links if 'rel="stylesheet"' in l.lower()])
            total_without_sri = len(scripts_without_sri) + len(links_without_sri)

            if total_external > 0 and total_without_sri > 0:
                issues.append(f'{total_without_sri}/{total_external} external resources missing SRI (integrity attribute)')
            elif total_external > 0:
                passes.append(f'All {total_external} external resources have SRI (integrity attribute)')
            else:
                passes.append('No external resources to check for SRI')

            if issues:
                severity = 'high' if http_scripts or http_links else 'medium'
                evidence_lines = ['ISSUES:'] + [f'  - {i}' for i in issues]
                if passes:
                    evidence_lines.append('PASSES:')
                    evidence_lines += [f'  + {p}' for p in passes]

                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity=severity,
                    description=f'Mixed content/SRI issues: {len(issues)} found',
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
                    description='Mixed content and SRI checks passed',
                    evidence=f'Passed: {", ".join(passes)}',
                    references=self.REFERENCES,
                ))

        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check mixed content/SRI: {e}',
            ))

        return results
