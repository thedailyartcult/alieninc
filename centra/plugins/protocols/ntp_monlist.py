"""
Plugin 1035: NTP Mode 6 Monlist Detection
============================================
Checks if NTP server allows mode 6 monlist queries (DDoS amplification).
Real CVEs: CVE-2023-31990, CVE-2021-4102
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class NtpMonlist(NaslPlugin):
    PLUGIN_ID = 1035
    NAME = 'NTP Mode 6 Monlist Detection'
    FAMILY = 'NTP'
    CVSS_SCORE = 5.0
    DESCRIPTION = (
        'The NTP server responds to mode 6 monlist queries from external sources. '
        'This can be abused for NTP amplification DDoS attacks, generating '
        'traffic amplification factors of up to 500x.'
    )
    SOLUTION = (
        'Disable NTP monlist query support. Use "noquery" or "restrict ... noquery" '
        'in ntp.conf. Upgrade to NTP 4.2.7p26+ which disables monlist by default.'
    )
    CVE = ['CVE-2023-31990', 'CVE-2021-4102']
    PORTS = [123]

    MONLIST_REQUEST = bytes([
        0x1a, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
    ])

    async def check_target(self, target: str, port: int | None = 123) -> list[PluginResult]:
        port = port or 123

        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: NtpProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )
            protocol.transport.sendto(self.MONLIST_REQUEST, (target, port))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 60:
                resp_count = struct.unpack('!H', data[40:42])[0]
                if resp_count > 0:
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description='NTP server responds to mode 6 monlist queries — amplification risk',
                        solution=self.SOLUTION,
                        evidence=f'NTP monlist response with {resp_count} entries ({len(data)} bytes)',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-31990',
                            'https://www.tenable.com/plugins/nessus/65891',
                        ]
                    )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='NTP server does not respond to mode 6 monlist queries'
        )]


class NtpProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.future = asyncio.Future()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc):
        if not self.future.done():
            self.future.set_exception(exc)
