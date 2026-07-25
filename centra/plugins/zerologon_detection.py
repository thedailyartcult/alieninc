"""
Plugin 1101: Microsoft Netlogon Privilege Escalation (ZeroLogon) (CVE-2020-1472)
=================================================================================
Detects ZeroLogon vulnerability in Microsoft Netlogon Remote Protocol.
Real CVE: CVE-2020-1472 (CVSS 10.0)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class ZerologonDetection(NaslPlugin):
    PLUGIN_ID = 1101
    NAME = 'Microsoft Netlogon Privilege Escalation (ZeroLogon) (CVE-2020-1472)'
    FAMILY = 'Windows'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'CVE-2020-1472, known as ZeroLogon, is a privilege escalation vulnerability '
        'in Microsoft Netlogon Remote Protocol (MS-NRPC). An unauthenticated attacker '
        'can establish a Netlogon secure channel using a zero-computed credential '
        'hash, then use domain admin privileges to compromise the entire domain. '
        'CVSS 10.0 - the maximum possible score.'
    )
    SOLUTION = (
        'Apply Microsoft November 2020 security update. Enforce full Secure RPC '
        'usage for domain controller connections. Set the '
        'FullSecureChannelProtection registry key.'
    )
    CVE = ['CVE-2020-1472']
    PORTS = [445, 135, 139]

    SMB_NEGOTIATE = (
        b'\x00\x00\x00\x90'
        b'\xfe\x53\x4d\x42'
        b'\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
        b'\x00\x00\x00\x00'
        b'\x02\x00\x00\x00'
        b'\x02\xff'
        b'\x00\x00'
    )

    async def _smb_probe(self, target: str, port: int) -> bytes | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=5
            )

            writer.write(self.SMB_NEGOTIATE)
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
            if port_to_check == 445:
                response = await self._smb_probe(target, port_to_check)
                if response is None:
                    continue

                smb_sig = response[4:8] if len(response) > 8 else b''
                smb_detected = smb_sig in (b'\xff\x53\x4d\x42', b'\xfe\x53\x4d\x42')

                if smb_detected:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='critical',
                        description=(
                            f'SMB service detected on port {port_to_check} — '
                            f'if this is a Windows Domain Controller, it may be vulnerable '
                            f'to ZeroLogon (CVE-2020-1472)'
                        ),
                        solution=self.SOLUTION,
                        evidence=(
                            f'SMB service detected via SMB negotiation response, '
                            f'potential Domain Controller indicator'
                        ),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2020-1472',
                            'https://www.tenable.com/plugins/nessus/142130',
                        ]
                    ))
            else:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check),
                        timeout=5
                    )
                    writer.close()
                    await writer.wait_closed()
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='critical',
                        description=(
                            f'Service detected on port {port_to_check} — '
                            f'if this is a Windows Domain Controller, it may be vulnerable '
                            f'to ZeroLogon (CVE-2020-1472)'
                        ),
                        solution=self.SOLUTION,
                        evidence=(
                            f'Port {port_to_check} is open, '
                            f'potential Domain Controller service'
                        ),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2020-1472',
                            'https://www.tenable.com/plugins/nessus/142130',
                        ]
                    ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ZeroLogon or Domain Controller indicators detected on checked ports'
            ))

        return results
