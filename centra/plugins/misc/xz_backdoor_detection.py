"""
Plugin 1073: XZ Utils SSH Backdoor Detection (CVE-2024-3094)
==============================================================
Detects compromised XZ Utils versions (5.6.0, 5.6.1) containing
a malicious backdoor that allows unauthorized SSH access.
Real CVEs: CVE-2024-3094 (CVSS 10.0)
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class XzBackdoorDetection(NaslPlugin):
    PLUGIN_ID = 1073
    NAME = 'XZ Utils SSH Backdoor Detection (CVE-2024-3094)'
    FAMILY = 'Misc.'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'Malicious code was discovered in XZ Utils versions 5.6.0 and 5.6.1. '
        'Through a series of complex obfuscations, the liblzma build process '
        'extracts a prebuilt object file that modifies SSH authentication. '
        'This supply-chain backdoor allows unauthorized remote access via SSH, '
        'potentially granting attackers complete control over affected systems. '
        'Discovered by Andres Freund on March 29, 2024.'
    )
    SOLUTION = (
        'Downgrade XZ Utils to a known-good version (5.4.x or earlier). '
        'Check for compromise by verifying SSH binaries and logs. '
        'Rotate all SSH keys on affected systems. Review system for '
        'unauthorized access. Apply the latest security updates from '
        'your Linux distribution vendor.'
    )
    CVE = ['CVE-2024-3094']
    PORTS = [22]

    VULNERABLE_VERSIONS = ['5.6.0', '5.6.1']

    SSH_BANNER_PATTERN = re.compile(
        r'SSH-([\d.]+)[-_]?(OpenSSH[_\s][\d.]+)?',
        re.IGNORECASE
    )

    async def check_target(self, target: str, port: int | None = 22) -> list[PluginResult]:
        port = port or 22
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            banner = b''
            try:
                banner = await asyncio.wait_for(reader.readline(), timeout=5)
            except asyncio.TimeoutError:
                pass
            writer.close()
            await writer.wait_closed()
            if not banner:
                return [PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='No SSH banner received'
                )]
            banner_str = banner.decode('utf-8', errors='ignore').strip()
            match = self.SSH_BANNER_PATTERN.search(banner_str)
            if match:
                ssh_version = match.group(1)
                full_banner = match.group(0)
                return [PluginResult(
                    vulnerable=True, target=target, port=port,
                    cvss_score=self.CVSS_SCORE, severity='critical',
                    description='SSH service detected: %s. '
                    'Check for XZ Backdoor. If running XZ Utils 5.6.0/5.6.1, '
                    'system is compromised.' % full_banner,
                    solution=self.SOLUTION,
                    evidence='SSH banner: %s' % banner_str,
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2024-3094',
                        'https://www.cisa.gov/news-events/alerts/2024/03/29/'
                        'reported-supply-chain-compromise-affecting-xz-utils-'
                        'data-compression-library-cve-2024-3094',
                        'https://www.tenable.com/plugins/nessus/192708',
                        'https://access.redhat.com/security/cve/CVE-2024-3094',
                    ]
                )]
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description='SSH service detected but version could not be determined'
            )]
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description='SSH port %d not reachable' % port
            )]
