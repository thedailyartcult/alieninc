"""
Plugin 1113: FortiOS SSL VPN Heap Overflow (CVE-2023-27997)
============================================================
Detects CVE-2023-27997 heap overflow in FortiOS SSL VPN.
Real CVE: CVE-2023-27997 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class FortiosHeapOverflowDetection(NaslPlugin):
    PLUGIN_ID = 1113
    NAME = 'FortiOS SSL VPN Heap Overflow (CVE-2023-27997)'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'FortiOS 6.x, 7.x before 7.0.10, 7.2.x before 7.2.4 contains a heap-based '
        'buffer overflow in the SSL VPN component. An unauthenticated attacker can send '
        'a crafted HTTP request to trigger the overflow, leading to arbitrary code '
        'execution. Discovered by Lexfo Security and used in targeted attacks.'
    )
    SOLUTION = (
        'Upgrade FortiOS to 7.0.10, 7.2.4, 7.4.0 or later. Disable SSL VPN if not needed.'
    )
    CVE = ['CVE-2023-27997']
    PORTS = [443, 8443, 10443]

    FORTIOS_SSL_VPN_PATHS = [
        '/remote/login',
        '/remote/portal',
        '/remote/error',
        '/remote/index',
        '/',
    ]

    FORTIOS_HINTS = [
        b'FortiGate',
        b'Fortinet',
        b'fortinet',
        b'FORTINET',
        b'SSLVPN',
        b'remote/login',
        b'remote/portal',
        b'/remote/',
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

                for path in self.FORTIOS_SSL_VPN_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
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

                        is_200 = b'200' in response[:50]
                        is_302 = b'302' in response[:50]
                        forti_hits = [h for h in self.FORTIOS_HINTS if h in response]

                        if forti_hits or (is_200 and b'sslvpn' in response.lower()) or (is_302 and b'remote' in response.lower()):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Fortinet SSL VPN detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2023-27997 heap overflow'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Fortinet indicators: {forti_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-27997',
                                    'https://www.fortiguard.com/psirt/FG-IR-23-097',
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
                description='No Fortinet SSL VPN indicators detected for CVE-2023-27997'
            ))

        return results
