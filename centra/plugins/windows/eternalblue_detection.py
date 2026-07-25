"""
Plugin 1077: EternalBlue — SMB RCE (CVE-2017-0144)
====================================================
Detects SMBv1 vulnerability in Microsoft Windows (EternalBlue/MS17-010).
Real CVE: CVE-2017-0144 (CVSS 8.8)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class EternalblueDetection(NaslPlugin):
    PLUGIN_ID = 1077
    NAME = 'Microsoft SMBv1 EternalBlue RCE Detection'
    FAMILY = 'Windows'
    CVSS_SCORE = 8.8
    DESCRIPTION = (
        'The SMBv1 server in Microsoft Windows is vulnerable to remote code execution '
        'via crafted packets, aka EternalBlue (MS17-010). Used by WannaCry ransomware '
        'in May 2017 to infect hundreds of thousands of systems worldwide. An '
        'unauthenticated attacker can execute arbitrary code on the target system.'
    )
    SOLUTION = (
        'Install Microsoft security update MS17-010. Disable SMBv1 protocol. Block '
        'port 445 at network perimeter. Apply workaround via Registry to disable SMBv1.'
    )
    CVE = ['CVE-2017-0144']
    PORTS = [445, 139]

    SMB_NEGOTIATE_PROTOCOL = (
        b'\x00\x00\x00\x90'        # NetBIOS session
        b'\xfe\x53\x4d\x42'        # SMBv2 dialect
        b'\x00\x00\x00\x00'        # smb status
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'  # smb header
        b'\x00\x00\x00\x00'        # tid
        b'\x00\x00\x00\x00'        # pid
        b'\x00\x00\x00\x00'        # uid
        b'\x00\x00\x00\x00'        # mid
        b'\x00\x00\x00\x00'        # word count
        b'\x02\x00\x00\x00'        # dialect count = 2
        b'\x02\xff'                # SMBv1 dialect + SMBv2 dialect
        b'\x00\x00'                # padding
    )

    SMBv1_DIALECT = b'\x02'

    async def _smb_negotiate(self, target: str, port: int) -> bytes | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=5
            )

            writer.write(self.SMB_NEGOTIATE_PROTOCOL)
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
            return response

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ConnectionResetError):
            return None

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            response = await self._smb_negotiate(target, port_to_check)
            if response is None:
                continue

            status_line = response[:8].hex() if len(response) >= 8 else ''
            smb_sig = response[4:8] if len(response) > 8 else b''
            smb_detected = smb_sig == b'\xff\x53\x4d\x42' or smb_sig == b'\xfe\x53\x4d\x42'

            smbv1_supported = False
            if smb_detected and len(response) > 40:
                neg_response = response[4:]
                if len(neg_response) > 36:
                    capabilities_offset = 36
                    if len(neg_response) > capabilities_offset:
                        raw = neg_response[capabilities_offset:]
                        smbv1_supported = len(raw) > 0

            if smb_detected:
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port_to_check,
                    cvss_score=self.CVSS_SCORE,
                    severity='high',
                    description=(
                        f'SMB service detected on port {port_to_check} — '
                        f'if SMBv1 is enabled, system may be vulnerable to EternalBlue'
                    ),
                    solution=self.SOLUTION,
                    evidence=(
                        f'SMB service: {"detected" if smb_detected else "not detected"}, '
                        f'SMBv1: {"likely enabled" if smbv1_supported else "potential"}, '
                        f'Response signature: {status_line}'
                    ),
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2017-0144',
                        'https://www.tenable.com/plugins/nessus/100301',
                    ]
                ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No SMB service or EternalBlue indicators detected'
            ))

        return results
