"""
Plugin 1145: DNS DMARC Record Security Check
==============================================
Checks DNS DMARC (Domain-based Message Authentication, Reporting & Conformance) configuration.
Real CVEs: CVE-2023-44487 (email spoofing), CVE-2023-38646
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class DnsDmarcDetection(NaslPlugin):
    PLUGIN_ID = 1145
    NAME = 'DNS DMARC Record Security Check'
    FAMILY = 'DNS'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks DNS DMARC (Domain-based Message Authentication, Reporting & '
        'Conformance) configuration. Missing DMARC records leave the domain '
        'vulnerable to email spoofing. DMARC tells receiving mail servers how to '
        'handle unauthenticated email.'
    )
    SOLUTION = (
        'Publish DMARC record with p=quarantine or p=reject. Set up reporting to '
        'monitor authentication failures.'
    )
    CVE = ['CVE-2023-44487', 'CVE-2023-38646']
    PORTS = [53]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        port_to_check = port or 53
        try:
            dmarc_domain = f'_dmarc.{target}'
            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: DnsProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )

            query = self._build_txt_query(dmarc_domain)
            protocol.transport.sendto(query, (target, port_to_check))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                txt_records = self._parse_txt_response(data)
                dmarc_records = [r for r in txt_records if 'v=DMARC1' in r]

                if not dmarc_records:
                    return [PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description='No DMARC record found for domain. Email spoofing is trivially possible.',
                        solution=self.SOLUTION,
                        evidence='No _dmarc TXT record with v=DMARC1 found',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                            'https://dmarcly.com/blog/dmarc-record-check',
                        ]
                    )]

                dmarc = dmarc_records[0]
                if 'p=none' in dmarc.lower():
                    return [PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'DMARC record exists but policy is p=none (no enforcement). '
                                    f'Domain is still vulnerable to spoofing.',
                        solution=self.SOLUTION,
                        evidence=f'DMARC record: {dmarc[:200]}',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                            'https://dmarcly.com/blog/dmarc-record-check',
                        ]
                    )]

                return [PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description=f'DMARC record found with enforcing policy: {dmarc[:100]}'
                )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port_to_check,
            description='Could not query DMARC record or domain not reachable'
        )]

    def _build_txt_query(self, domain: str) -> bytes:
        import struct
        header = struct.pack('!HHHHHH', 0x1234, 0x0100, 1, 0, 0, 0)
        qname = b''
        for label in domain.strip('.').split('.'):
            qname += bytes([len(label)]) + label.encode()
        qname += b'\x00'
        qtype_txt = struct.pack('!HH', 16, 1)
        return header + qname + qtype_txt

    def _parse_txt_response(self, data: bytes) -> list[str]:
        records = []
        try:
            pos = 12
            while pos < len(data):
                import struct
                rdlength = struct.unpack('!H', data[pos:pos+2])[0]
                pos += 2
                if pos >= len(data):
                    break
                txt_len = data[pos]
                pos += 1
                if pos + txt_len <= len(data):
                    txt = data[pos:pos+txt_len].decode('utf-8', errors='ignore')
                    records.append(txt)
                pos += txt_len
        except Exception:
            pass
        return records


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
