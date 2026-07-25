"""
Plugin 1033: Open DNS Resolver Detection
===========================================
Detects DNS servers that perform recursive resolution for external clients.
Real CVEs: CVE-2023-29552, CVE-2021-25216
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class OpenDnsResolver(NaslPlugin):
    PLUGIN_ID = 1033
    NAME = 'Open DNS Resolver Detection'
    FAMILY = 'DNS'
    CVSS_SCORE = 5.0
    DESCRIPTION = (
        'The DNS server responds to recursive queries from external sources. '
        'Open resolvers can be abused for DNS amplification DDoS attacks, '
        'enabling attackers to generate large traffic volumes toward victims.'
    )
    SOLUTION = (
        'Restrict DNS recursion to trusted internal networks only. '
        'Use allow-recursion ACLs in BIND or equivalent settings. '
        'Disable recursion entirely if not required.'
    )
    CVE = ['CVE-2023-29552', 'CVE-2021-25216']
    PORTS = [53]

    async def check_target(self, target: str, port: int | None = 53) -> list[PluginResult]:
        port = port or 53

        try:
            txid = 0x5678
            query = self._build_recursive_query(txid)
            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: DnsProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )
            protocol.transport.sendto(query, (target, port))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                resp_txid = struct.unpack('!H', data[0:2])[0]
                an_count = struct.unpack('!H', data[6:8])[0]
                if resp_txid == txid and an_count > 0:
                    return [PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description='DNS server is an open resolver — usable for amplification attacks',
                        solution=self.SOLUTION,
                        evidence=f'Recursive query returned {an_count} answer record(s)',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-29552',
                            'https://www.tenable.com/plugins/nessus/57437',
                        ]
                    )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='DNS server does not appear to be an open resolver'
        )]

    def _build_recursive_query(self, txid: int) -> bytes:
        header = struct.pack('!HHHHHH', txid, 0x0100, 1, 0, 0, 0)
        qname = b'\x03www\x07example\x03com\x00'
        qtype = struct.pack('!HH', 1, 1)
        return header + qname + qtype


class DnsProtocol(asyncio.DatagramProtocol):
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
