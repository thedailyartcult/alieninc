"""
Plugin 1102: Windows Print Spooler RCE (PrintNightmare) (CVE-2021-1675)
========================================================================
Detects PrintNightmare vulnerability in Windows Print Spooler service.
Real CVEs: CVE-2021-1675, CVE-2021-34527 (CVSS 8.8)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class PrintnightmareDetection(NaslPlugin):
    PLUGIN_ID = 1102
    NAME = 'Windows Print Spooler RCE (PrintNightmare) (CVE-2021-1675)'
    FAMILY = 'Windows'
    CVSS_SCORE = 8.8
    DESCRIPTION = (
        'CVE-2021-1675 / CVE-2021-34527, known as PrintNightmare, is a remote '
        'code execution vulnerability in the Windows Print Spooler service. An '
        'authenticated attacker can remotely execute arbitrary code with SYSTEM '
        'privileges by sending a crafted print request. Highly exploited in the '
        'wild by ransomware groups.'
    )
    SOLUTION = (
        'Apply Microsoft security updates. Disable Print Spooler service if not '
        'needed. Set the RestrictDriverInstallationToAdministrators registry key.'
    )
    CVE = ['CVE-2021-1675', 'CVE-2021-34527']
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
            if port_to_check in (445, 139):
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
                        severity='high',
                        description=(
                            f'SMB service detected on port {port_to_check} — '
                            f'if Print Spooler service is running, system may be '
                            f'vulnerable to PrintNightmare (CVE-2021-1675 / CVE-2021-34527)'
                        ),
                        solution=self.SOLUTION,
                        evidence=(
                            f'SMB service detected, '
                            f'potential Print Spooler named pipe access'
                        ),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2021-1675',
                            'https://nvd.nist.gov/vuln/detail/CVE-2021-34527',
                            'https://www.tenable.com/plugins/nessus/151317',
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
                        severity='high',
                        description=(
                            f'Service detected on port {port_to_check} — '
                            f'potential Print Spooler RPC endpoint'
                        ),
                        solution=self.SOLUTION,
                        evidence=(
                            f'Port {port_to_check} is open'
                        ),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2021-1675',
                            'https://nvd.nist.gov/vuln/detail/CVE-2021-34527',
                            'https://www.tenable.com/plugins/nessus/151317',
                        ]
                    ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Print Spooler or PrintNightmare indicators detected on checked ports'
            ))

        return results
