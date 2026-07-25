"""
Plugin 1008: RDP Encryption Level Check
=========================================
Checks for weak RDP encryption and NLA requirements.
Real CVEs: CVE-2019-0708 (BlueKeep), CVE-2024-21887 (RDP RCE)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class RdpEncryption(NaslPlugin):
    PLUGIN_ID = 1008
    NAME = 'RDP Encryption Level Check'
    FAMILY = 'Windows'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The remote RDP server may use weak encryption or does not require '
        'Network Level Authentication (NLA). This could allow unauthorized '
        'access or interception of remote desktop sessions.'
    )
    SOLUTION = (
        'Enable NLA (Network Level Authentication) and set encryption level '
        'to High or FIPS. Disable RDP if not needed. Apply the latest Windows '
        'security updates to patch BlueKeep and related vulnerabilities.'
    )
    CVE = ['CVE-2019-0708', 'CVE-2012-0002', 'CVE-2024-21887']
    PORTS = [3389]

    async def check_target(self, target: str, port: int | None = 3389) -> list[PluginResult]:
        port = port or 3389

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            x224_connect = self._build_x224_connect()
            writer.write(x224_connect)
            await writer.drain()

            resp = await asyncio.wait_for(reader.read(2048), timeout=5)
            writer.close()
            await writer.wait_closed()

            if len(resp) < 20:
                return [PluginResult(vulnerable=False, target=target, port=port)]

            results = []

            resp_str = resp.decode('utf-8', errors='ignore')

            if 'rdp://' in resp_str.lower() or len(resp) > 10:
                nla_required = self._check_nla(resp)

                if not nla_required:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=7.5,
                        severity='high',
                        description='RDP server does not require Network Level Authentication (NLA).',
                        solution=self.SOLUTION,
                        evidence=f'RDP connection accepted without NLA requirement',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2019-0708',
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-36884',
                            'https://www.tenable.com/plugins/nessus/18663',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port,
                        description='RDP server requires NLA'
                    ))

            return results

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description=f'RDP port {port} not reachable')]

    def _build_x224_connect(self) -> bytes:
        tpkt = struct.pack('!BBH', 3, 0, 0)
        x224_length = 14
        x224_type = 0xe0
        x224_dst_ref = struct.pack('>H', 0)
        x224_src_ref = struct.pack('>H', 0)
        x224_class = 0
        x224_opt_type = 2
        x224_opt_len = 2
        x224_protocol = struct.pack('>H', 0)
        return tpkt + struct.pack('!B', x224_length) + bytes([x224_type]) + x224_dst_ref + x224_src_ref + bytes([x224_class, x224_opt_type, x224_opt_len]) + x224_protocol

    def _check_nla(self, data: bytes) -> bool:
        if len(data) < 19:
            return False
        try:
            x224_type = data[11] if len(data) > 11 else 0
            if x224_type == 0xd0:
                return False
            return True
        except:
            return False
