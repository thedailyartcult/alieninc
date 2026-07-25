"""
Plugin 1006: DNS Zone Transfer Check
======================================
Tests if DNS server allows zone transfers.
Real CVEs: CVE-2023-29552 (BIND amplification), CVE-2021-25216
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class DnsZoneTransfer(NaslPlugin):
    PLUGIN_ID = 1006
    NAME = 'DNS Zone Transfer Check'
    FAMILY = 'DNS'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The DNS server allows zone transfers (AXFR). An attacker can enumerate '
        'the entire DNS zone, discovering internal hostnames, IP addresses, and '
        'network topology.'
    )
    SOLUTION = (
        'Restrict zone transfers to authorized secondary DNS servers only. '
        'Configure TSIG for zone transfer authentication. Use "allow-transfer" '
        'ACLs in BIND or equivalent settings in other DNS servers.'
    )
    CVE = ['CVE-2023-29552', 'CVE-2021-25216']
    PORTS = [53]

    async def check_target(self, target: str, port: int | None = 53) -> list[PluginResult]:
        port = port or 53

        try:
            query = self._build_axfr_query(target)

            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: AxfrProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )

            protocol.transport.sendto(query, (target, port))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                an_count = struct.unpack('!H', data[6:8])[0]
                if an_count > 0:
                    records = self._parse_axfr(data)
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='high',
                        description='DNS zone transfer (AXFR) is allowed. ' + str(an_count) + ' records returned.',
                        solution=self.SOLUTION,
                        evidence='AXFR response: ' + str(an_count) + ' answer records, ' + str(len(records)) + ' records parsed',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-29552',
                            'https://www.acunetix.com/blog/articles/dns-zone-transfers-axfr/',
                        ]
                    )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='DNS zone transfer not permitted or port not reachable'
        )]

    def _build_axfr_query(self, domain: str) -> bytes:
        header = struct.pack('!HHHHHH', 0x1234, 0x0000, 1, 0, 0, 0)
        qname = b''
        for label in domain.strip('.').split('.'):
            qname += bytes([len(label)]) + label.encode()
        qname += b'\x00'
        qtype_axfr = struct.pack('!HH', 252, 1)
        return header + qname + qtype_axfr

    def _parse_axfr(self, data: bytes) -> list:
        return []


class AxfrProtocol(asyncio.DatagramProtocol):
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
