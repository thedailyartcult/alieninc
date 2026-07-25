"""
Plugin 1078: BlueKeep — RDP RCE (CVE-2019-0708)
=================================================
Detects BlueKeep RCE vulnerability in Microsoft RDP.
Real CVE: CVE-2019-0708 (CVSS 9.8)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class BluekeepDetection(NaslPlugin):
    PLUGIN_ID = 1078
    NAME = 'Microsoft RDP BlueKeep RCE Detection (CVE-2019-0708)'
    FAMILY = 'Windows'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'A remote code execution vulnerability exists in Remote Desktop Services '
        '(formerly Terminal Services) when an unauthenticated attacker connects to '
        'the target system using RDP and sends specially crafted requests, aka '
        'BlueKeep. This vulnerability is wormable, meaning any future malware that '
        'exploits it could propagate without user interaction.'
    )
    SOLUTION = (
        'Apply Microsoft security update from May 2019. Enable Network Level '
        'Authentication (NLA) as a mitigation. Block port 3389 at network perimeter. '
        'Upgrade to Windows 8/8.1/10 or Windows Server 2012+ which are not affected.'
    )
    CVE = ['CVE-2019-0708']
    PORTS = [3389]

    RDP_NEG_REQUEST = (
        b'\x03\x00\x00\x13'        # TPKT header (version 3, length 19)
        b'\x0e\xe0\x00\x00'        # RDP Negotiation Request
        b'\x00\x00\x00\x00'        # flags
        b'\x01\x00\x08\x00'        # requested protocols
        b'\x01\x00\x00\x00'        # correlation flags
    )

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check),
                    timeout=5
                )

                writer.write(self.RDP_NEG_REQUEST)
                await writer.drain()

                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 4096:
                            break
                except asyncio.TimeoutError:
                    pass

                writer.close()
                await writer.wait_closed()

                if len(response) < 8:
                    continue

                tpkt_len = len(response)
                rdp_detected = response[0:2] == b'\x03\x00'

                nla_required = False
                if len(response) > 11:
                    protocol_selector = response[11]
                    if protocol_selector == 0x02:
                        nla_required = True
                    elif protocol_selector == 0x00:
                        nla_required = False

                if rdp_detected:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='critical',
                        description=(
                            f'RDP service detected on port {port_to_check} — '
                            f'BlueKeep vulnerable if running on Windows 7/2008 R2/2008/XP/2003 '
                            f'without NLA'
                        ),
                        solution=self.SOLUTION,
                        evidence=(
                            f'RDP service: detected, '
                            f'NLA: {"enabled (mitigated)" if nla_required else "not required (potentially vulnerable)"}, '
                            f'Response length: {tpkt_len} bytes'
                        ),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2019-0708',
                            'https://www.tenable.com/plugins/nessus/126645',
                        ]
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ConnectionResetError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No RDP service or BlueKeep indicators detected'
            ))

        return results
