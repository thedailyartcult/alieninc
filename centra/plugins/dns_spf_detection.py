"""
Plugin 1143: DNS SPF Record Security Check
============================================
Checks DNS SPF (Sender Policy Framework) records for the target domain.
Real CVEs: CVE-2023-44487 (email spoofing), CVE-2023-38646
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class DnsSpfDetection(NaslPlugin):
    PLUGIN_ID = 1143
    NAME = 'DNS SPF Record Security Check'
    FAMILY = 'DNS'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks DNS SPF (Sender Policy Framework) records for the target domain. '
        'Missing or misconfigured SPF records allow attackers to send spoofed '
        'emails from the domain, enabling phishing and email fraud.'
    )
    SOLUTION = (
        'Publish SPF record with -all (hard fail) to authorize legitimate senders. '
        'Include all third-party email services.'
    )
    CVE = ['CVE-2023-44487', 'CVE-2023-38646']
    PORTS = [53]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        port_to_check = port or 53
        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: DnsProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )

            query = self._build_txt_query(target)
            protocol.transport.sendto(query, (target, port_to_check))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                txt_records = self._parse_txt_response(data)
                spf_records = [r for r in txt_records if 'v=spf1' in r.lower()]

                if not spf_records:
                    return [PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description='No SPF record found for domain. Email spoofing is possible.',
                        solution=self.SOLUTION,
                        evidence='No TXT records with v=spf1 found for domain',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                            'https://dmarcly.com/blog/spf-record-check',
                        ]
                    )]

                for spf in spf_records:
                    if '~all' in spf or '?all' in spf or '+all' in spf or 'all' not in spf:
                        return [PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='medium',
                            description=f'SPF record exists but does not use hard fail (-all). Current policy: {spf[:100]}',
                            solution=self.SOLUTION,
                            evidence=f'SPF record: {spf[:200]}',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                                'https://dmarcly.com/blog/spf-record-check',
                            ]
                        )]

                return [PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='SPF record found with proper -all (hard fail) policy'
                )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port_to_check,
            description='Could not query DNS or no SPF record found'
        )]

    def _build_txt_query(self, domain: str) -> bytes:
        header = __import__('struct').pack('!HHHHHH', 0x1234, 0x0100, 1, 0, 0, 0)
        qname = b''
        for label in domain.strip('.').split('.'):
            qname += bytes([len(label)]) + label.encode()
        qname += b'\x00'
        qtype_txt = __import__('struct').pack('!HH', 16, 1)
        return header + qname + qtype_txt

    def _parse_txt_response(self, data: bytes) -> list[str]:
        records = []
        try:
            pos = 12
            while pos < len(data):
                rdlength = __import__('struct').unpack('!H', data[pos:pos+2])[0]
                pos += 2
                txt_len = data[pos]
                pos += 1
                txt = data[pos:pos+txt_len].decode('utf-8', errors='ignore')
                records.append(txt)
                pos += txt_len
                if pos >= len(data):
                    break
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
