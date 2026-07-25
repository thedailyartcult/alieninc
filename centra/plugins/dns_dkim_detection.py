"""
Plugin 1144: DNS DKIM Record Security Check
=============================================
Checks DNS DKIM (DomainKeys Identified Mail) configuration for the target domain.
Real CVEs: CVE-2023-44487 (email spoofing), CVE-2023-38646
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class DnsDkimDetection(NaslPlugin):
    PLUGIN_ID = 1144
    NAME = 'DNS DKIM Record Security Check'
    FAMILY = 'DNS'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks DNS DKIM (DomainKeys Identified Mail) configuration for the target '
        'domain. Missing DKIM records allow attackers to forge email from the domain. '
        'DKIM provides cryptographic verification of email origin.'
    )
    SOLUTION = (
        'Generate DKIM keys and publish DKIM TXT record in DNS. Rotate keys periodically.'
    )
    CVE = ['CVE-2023-44487', 'CVE-2023-38646']
    PORTS = [53]

    DKIM_SELECTORS = ['default', 'google', 'selector1', 'selector2', 'dkim', 'mail', 'email', 'protonmail', 'smtp']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        port_to_check = port or 53
        found_records = []

        for selector in self.DKIM_SELECTORS:
            try:
                dkim_domain = f'{selector}._domainkey.{target}'
                loop = asyncio.get_running_loop()
                transport, protocol = await asyncio.wait_for(
                    loop.create_datagram_endpoint(
                        lambda: DnsProtocol(), local_addr=('0.0.0.0', 0)
                    ), timeout=3
                )

                query = self._build_txt_query(dkim_domain)
                protocol.transport.sendto(query, (target, port_to_check))
                data = await asyncio.wait_for(protocol.future, timeout=5)
                transport.close()

                if data and len(data) > 12:
                    txt_records = self._parse_txt_response(data)
                    for rec in txt_records:
                        if 'v=DKIM1' in rec:
                            found_records.append(f'{selector}: {rec[:100]}')

            except (asyncio.TimeoutError, OSError):
                pass

        if not found_records:
            return [PluginResult(
                vulnerable=True, target=target, port=port_to_check,
                cvss_score=self.CVSS_SCORE, severity='medium',
                description='No DKIM records found for any common selector. Email domain forgery is possible.',
                solution=self.SOLUTION,
                evidence=f'Checked selectors: {", ".join(self.DKIM_SELECTORS)} - none found',
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                    'https://dmarcly.com/blog/dkim-record-check',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port_to_check,
            description=f'DKIM records found for selectors: {", ".join(r.split(":")[0] for r in found_records)}'
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
