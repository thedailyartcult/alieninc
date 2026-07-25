"""
Plugin 1007: SMB Signing Not Required
=======================================
Detects SMB servers that don't require message signing.
Real CVEs: CVE-2023-21554 (MoTW), CVE-2017-0144 (EternalBlue)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class SmbSigning(NaslPlugin):
    PLUGIN_ID = 1007
    NAME = 'SMB Signing Not Required'
    FAMILY = 'Windows'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The remote SMB server does not require message signing. This exposes '
        'the service to man-in-the-middle attacks where an attacker can intercept '
        'or modify SMB traffic.'
    )
    SOLUTION = (
        'Enable SMB signing on the server. On Windows, configure via Group Policy: '
        'Computer Configuration > Policies > Windows Settings > Security Settings > '
        'Local Policies > Security Options > "Microsoft network server: Digitally '
        'sign communications (always)". For Samba, set "server signing = mandatory".'
    )
    CVE = ['CVE-2023-21554', 'CVE-2017-0144', 'CVE-2008-4810']
    PORTS = [445, 139]

    async def check_target(self, target: str, port: int | None = 445) -> list[PluginResult]:
        if port not in (445, 139):
            return []
        port = port or 445

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            negotiate_proto = self._build_negotiate()
            writer.write(negotiate_proto)
            await writer.drain()

            resp = await asyncio.wait_for(reader.read(1024), timeout=5)
            writer.close()
            await writer.wait_closed()

            if len(resp) >= 36:
                flags = resp[30]
                signing_enabled = bool(flags & 0x08)
                signing_required = bool(flags & 0x04)

                if signing_enabled and not signing_required:
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='high',
                        description='SMB signing is enabled but not required. MITM attacks possible.',
                        solution=self.SOLUTION,
                        evidence='SMB Negotiate: signing_enabled=True, signing_required=False (flags=0x{:02x})'.format(flags),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-21554',
                            'https://www.tenable.com/plugins/nessus/57608',
                        ]
                    )]
                elif not signing_enabled:
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='high',
                        description='SMB signing is not supported by the server.',
                        solution=self.SOLUTION,
                        evidence='SMB Negotiate: signing_enabled=False (flags=0x{:02x})'.format(flags),
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2017-0144',
                        ]
                    )]

            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='SMB signing is required')]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description=f'SMB port {port} not reachable')]

    def _build_negotiate(self) -> bytes:
        netbios = struct.pack('!BBBB', 0x00, 0x00, 0x00, 0x45)
        smb_header = b'\xffSMB'
        smb_header += struct.pack('<B', 0x72)
        smb_header += b'\x00' * 3
        smb_header += struct.pack('<H', 0x98)
        smb_header += b'\x00' * 2
        smb_header += struct.pack('<H', 0x00)
        smb_header += b'\x00' * 2
        smb_header += struct.pack('<HH', 0xc853, 0x0031)
        smb_header += b'\x00' * 8
        smb_header += struct.pack('<Q', 0x1122334455667788)
        dialects = b'\x02NT LM 0.12\x00\x02SMB 2.002\x00\x02SMB 2.1\x00\x02SMB 2.2\x00\x02SMB 2.FF\x00'
        return netbios + smb_header + dialects
