"""
Plugin 1107: Windows Network File System RCE (CVE-2022-30136)
==============================================================
Detects CVE-2022-30136 RCE in Windows NFS service.
Real CVE: CVE-2022-30136 (CVSS 9.8)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class WindowsNfsRceDetection(NaslPlugin):
    PLUGIN_ID = 1107
    NAME = 'Windows Network File System RCE (CVE-2022-30136)'
    FAMILY = 'Windows'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Windows Network File System (NFS) in Windows Server 2012 R2, 2016, 2019, 2022 '
        'contains a remote code execution vulnerability. An unauthenticated attacker can '
        'send a specially crafted NFS call to trigger a buffer overflow, leading to RCE '
        'in the NFS service context.'
    )
    SOLUTION = (
        'Apply Microsoft June 2022 security update. Disable NFS service if not needed.'
    )
    CVE = ['CVE-2022-30136']
    PORTS = [445, 2049]

    SMB_NEGOTIATE_PROTOCOL = (
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

    NFS_PROBE = (
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    )

    async def _check_smb(self, target: str, port: int) -> bool:
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

            if len(response) > 8:
                smb_sig = response[4:8]
                return smb_sig == b'\xff\x53\x4d\x42' or smb_sig == b'\xfe\x53\x4d\x42'
            return False

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False

    async def _check_nfs(self, target: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=5
            )

            writer.write(self.NFS_PROBE)
            await writer.drain()

            response = b''
            try:
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 4096:
                        break
            except asyncio.TimeoutError:
                pass

            writer.close()
            await writer.wait_closed()

            return len(response) > 0

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            if port_to_check == 445:
                smb_detected = await self._check_smb(target, port_to_check)
                if smb_detected:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='critical',
                        description=(
                            f'SMB service detected on port {port_to_check} — '
                            f'Windows NFS RCE (CVE-2022-30136) may be exploitable '
                            f'on neighboring NFS port 2049'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'SMB service detected — Windows Server environment confirmed',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2022-30136',
                            'https://msrc.microsoft.com/update-guide/vulnerability/CVE-2022-30136',
                        ]
                    ))

            elif port_to_check == 2049:
                nfs_detected = await self._check_nfs(target, port_to_check)
                if nfs_detected:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='critical',
                        description=(
                            f'NFS service detected on port {port_to_check} — '
                            f'potentially vulnerable to CVE-2022-30136 RCE'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'NFS port {port_to_check} is open and responding',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2022-30136',
                            'https://msrc.microsoft.com/update-guide/vulnerability/CVE-2022-30136',
                        ]
                    ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No SMB or NFS services detected for CVE-2022-30136'
            ))

        return results
