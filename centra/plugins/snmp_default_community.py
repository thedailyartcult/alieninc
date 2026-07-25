"""
Plugin 1034: SNMP Default Community String
=============================================
Detects SNMP services using default community strings (public/private).
Uses proper ASN.1 BER-encoded SNMPv2c GetRequest packets.
Real CVEs: CVE-1999-0517 (SNMP default community)
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class SnmpDefaultCommunity(NaslPlugin):
    PLUGIN_ID = 1034
    NAME = 'SNMP Default Community String'
    FAMILY = 'SNMP'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The SNMP service responds with a default community string ("public" or '
        '"private"). This allows attackers to read (and potentially write) system '
        'configuration, network topology, and device information.'
    )
    SOLUTION = (
        'Change default SNMP community strings to hard-to-guess values. '
        'Use SNMPv3 with authentication and encryption. Restrict SNMP access '
        'by IP address via SNMP ACLs.'
    )
    CVE = ['CVE-1999-0517']
    PORTS = [161]

    COMMUNITIES = ['public', 'private', 'snmp', 'admin', 'manager', 'cable', 'write']

    SYS_DESCR_OID = bytes([0x2b, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00])

    async def check_target(self, target: str, port: int | None = 161) -> list[PluginResult]:
        port = port or 161

        for community in self.COMMUNITIES:
            try:
                pkt = self._build_snmpv2c_get(community, 0x12345678)
                loop = asyncio.get_running_loop()
                transport, protocol = await asyncio.wait_for(
                    loop.create_datagram_endpoint(
                        lambda: SnmpProtocol(), local_addr=('0.0.0.0', 0)
                    ), timeout=3
                )
                try:
                    protocol.transport.sendto(pkt, (target, port))
                    data = await asyncio.wait_for(protocol.future, timeout=4)
                finally:
                    transport.close()

                if data and len(data) > 15:
                    if self._is_valid_snmp_response(data, 0x12345678):
                        return [PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port,
                            cvss_score=self.CVSS_SCORE,
                            severity='high',
                            description=f'SNMP responds with default community: "{community}"',
                            solution=self.SOLUTION,
                            evidence=f'Valid SNMP response with community "{community}" on port {port} ({len(data)} bytes)',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2023-38114',
                                'https://www.tenable.com/plugins/nessus/10470',
                            ]
                        )]

            except (asyncio.TimeoutError, OSError):
                pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='SNMP does not respond with default community strings'
        )]

    def _build_snmpv2c_get(self, community: str, req_id: int) -> bytes:
        def ber_length(length: int) -> bytes:
            if length < 128:
                return bytes([length])
            return bytes([0x81, length])

        oid_tag = b'\x06' + bytes([len(self.SYS_DESCR_OID)]) + self.SYS_DESCR_OID
        null_tag = b'\x05\x00'
        varbind = b'\x30' + ber_length(len(oid_tag) + len(null_tag)) + oid_tag + null_tag
        varbind_list = b'\x30' + ber_length(len(varbind)) + varbind

        rid = struct.pack('!I', req_id)
        error = b'\x02\x01\x00\x02\x01\x00'
        pdu_body = rid + error + varbind_list
        pdu = b'\xa0' + ber_length(len(pdu_body)) + pdu_body

        version = b'\x02\x01\x01'
        comm_bytes = community.encode()
        community_tag = b'\x04' + bytes([len(comm_bytes)]) + comm_bytes
        inner = version + community_tag + pdu
        outer = b'\x30' + ber_length(len(inner)) + inner
        return outer

    def _is_valid_snmp_response(self, data: bytes, expected_req_id: int) -> bool:
        try:
            if len(data) < 20:
                return False
            if data[0] != 0x30:
                return False
            pdu_type = data[8:12] if len(data) > 12 else b''
            if pdu_type[0] not in (0xa0, 0xa1, 0xa2):
                return False
            return True
        except Exception:
            return False


class SnmpProtocol(asyncio.DatagramProtocol):
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
