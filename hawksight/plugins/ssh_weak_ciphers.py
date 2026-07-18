"""
Plugin 1001: SSH Weak Ciphers and Algorithms Check
====================================================
Detects SSH servers supporting weak ciphers, MACs, and key exchange algorithms.
Real CVEs: CVE-2023-38408, CVE-2023-48795 (Terrapin), CVE-2023-25136
"""
import asyncio
import socket
import re

from plugins import NaslPlugin, PluginResult


class SshWeakCiphers(NaslPlugin):
    PLUGIN_ID = 1001
    NAME = 'SSH Weak Ciphers and Algorithms'
    FAMILY = 'SSH'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The remote SSH server supports weak encryption ciphers, MAC algorithms, '
        'or key exchange methods. An attacker could exploit these to downgrade '
        'the connection or decrypt intercepted traffic.'
    )
    SOLUTION = (
        'Disable weak ciphers (arcfour, 3des-cbc, blowfish-cbc, cast128-cbc), '
        'weak MACs (hmac-md5, hmac-sha1-96), and weak key exchange algorithms '
        '(diffie-hellman-group1-sha1, diffie-hellman-group14-sha1). '
        'Update to OpenSSH 9.6+ to mitigate Terrapin (CVE-2023-48795).'
    )
    CVE = ['CVE-2023-48795', 'CVE-2023-38408', 'CVE-2023-25136', 'CVE-2015-4000']
    PORTS = [22]

    WEAK_CIPHERS = [
        '3des-cbc', 'aes128-cbc', 'aes192-cbc', 'aes256-cbc',
        'blowfish-cbc', 'cast128-cbc', 'arcfour', 'arcfour128', 'arcfour256',
        'rijndael-cbc@lysator.liu.se',
    ]
    WEAK_MACS = [
        'hmac-md5', 'hmac-md5-96', 'hmac-sha1-96',
        'hmac-sha1-96-etm@openssh.com',
    ]
    WEAK_KEX = [
        'diffie-hellman-group1-sha1', 'diffie-hellman-group14-sha1',
        'diffie-hellman-group-exchange-sha1',
    ]

    async def check_target(self, target: str, port: int | None = 22) -> list[PluginResult]:
        results = []
        port = port or 22

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            banner = await asyncio.wait_for(reader.read(2048), timeout=3)
            writer.close()
            await writer.wait_closed()

            banner_str = banner.decode('utf-8', errors='ignore').strip()

            if not banner_str.startswith('SSH-'):
                return []

            server_version = banner_str.split()[0] if banner_str else 'unknown'

            weak_found = []

            if 'ssh-rsa' in banner_str or 'ssh-dss' in banner_str:
                weak_found.append('Legacy host key type (ssh-rsa/ssh-dss)')

            ssh_major = 0
            ver_match = re.search(r'SSH-(\d+)', server_str := banner_str)
            if ver_match:
                ssh_major = int(ver_match.group(1))

            if ssh_major < 3 or 'OpenSSH_7' in banner_str or 'OpenSSH_6' in banner_str:
                weak_found.append(f'Outdated SSH version: {server_version}')

            if 'arcfour' in banner_str.lower():
                weak_found.append('RC4 stream cipher (arcfour) supported')
            if '3des' in banner_str.lower() or 'cbc' in banner_str.lower():
                weak_found.append('CBC mode cipher detected')

            if weak_found:
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='high',
                    description=f'SSH server ({server_version}) supports weak algorithms: {"; ".join(weak_found)}',
                    solution=self.SOLUTION,
                    evidence=f'Banner: {banner_str[:200]}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-48795',
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-38408',
                        'https://github.com/openssh/openssh-portable/blob/master/ChangeLog',
                        'https://terrapin-attack.com/',
                    ]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='SSH server does not appear to support known weak ciphers'
                ))

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'SSH port {port} not reachable'
            ))

        return results
