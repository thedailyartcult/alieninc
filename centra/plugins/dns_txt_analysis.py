"""
Plugin 1146: DNS TXT Record Information Disclosure
=====================================================
Analyzes DNS TXT records for potential information disclosure.
"""
import asyncio
import struct
import re

from plugins import NaslPlugin, PluginResult


class DnsTxtAnalysis(NaslPlugin):
    PLUGIN_ID = 1146
    NAME = 'DNS TXT Record Information Disclosure'
    FAMILY = 'DNS'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Analyzes DNS TXT records for the target domain for potential information '
        'disclosure. TXT records may inadvertently leak internal information, '
        'infrastructure details, or sensitive strings.'
    )
    SOLUTION = (
        'Review all TXT records for sensitive information. Remove unnecessary '
        'TXT records. Keep only required SPF, DKIM, DMARC, and verification records.'
    )
    CVE = []
    PORTS = [53]

    SENSITIVE_PATTERNS = [
        (r'internal', 'Internal network reference'),
        (r'admin', 'Admin-related string'),
        (r'password', 'Password string'),
        (r'secret', 'Secret string'),
        (r'token', 'Token string'),
        (r'api[_-]?key', 'API key pattern'),
        (r'access[_-]?key', 'Access key pattern'),
        (r'private', 'Private key reference'),
        (r'credential', 'Credential string'),
        (r'ssh[_-]?key', 'SSH key reference'),
        (r'pwd\b', 'Password abbreviation'),
        (r'vpn', 'VPN configuration'),
        (r'db[_-]?(host|name|user)', 'Database configuration'),
        (r'jenkins', 'Jenkins CI reference'),
        (r'aws[_-]?secret', 'AWS secret reference'),
        (r'cloudfront', 'CloudFront distribution'),
        (r'connection[_-]?string', 'Connection string'),
    ]

    async def check_target(self, target: str, port: int | None = 53) -> list[PluginResult]:
        port = port or 53

        domain = target
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', target):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Target is an IP address, DNS TXT records not applicable')]

        try:
            query = self._build_txt_query(domain)

            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: DnsTxtProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )

            protocol.transport.sendto(query, (target, port))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                txt_records = self._parse_txt_records(data)
                if txt_records:
                    findings = []
                    for record in txt_records:
                        for pattern, label in self.SENSITIVE_PATTERNS:
                            if re.search(pattern, record, re.IGNORECASE):
                                findings.append(f'{label}: "{record[:100]}"')
                                break

                    if findings:
                        return [PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description=f'Sensitive content in TXT records: {len(findings)} pattern(s) matched',
                            solution=self.SOLUTION,
                            evidence='; '.join(findings[:5]),
                            references=[
                                'https://datatracker.ietf.org/doc/html/rfc1035',
                                'https://www.tenable.com/plugins/nessus/10656',
                            ]
                        )]
                    else:
                        return [PluginResult(
                            vulnerable=False, target=target, port=port,
                            description=f'{len(txt_records)} TXT record(s) found, no sensitive content detected'
                        )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No TXT records found or DNS server not reachable'
        )]

    def _build_txt_query(self, domain: str) -> bytes:
        header = struct.pack('!HHHHHH', 0x1234, 0x0100, 1, 0, 0, 0)
        qname = b''
        for label in domain.strip('.').split('.'):
            qname += bytes([len(label)]) + label.encode()
        qname += b'\x00'
        qtype_txt = struct.pack('!HH', 16, 1)
        return header + qname + qtype_txt

    def _parse_txt_records(self, data: bytes) -> list[str]:
        records = []
        try:
            header_len = 12
            pos = header_len
            while pos < len(data):
                label_len = data[pos]
                if label_len == 0:
                    pos += 1
                    break
                pos += 1 + label_len

            pos += 4
            ancount = struct.unpack('!H', data[6:8])[0]

            for _ in range(ancount):
                if pos >= len(data):
                    break
                if data[pos] & 0xC0:
                    pos += 2
                else:
                    while pos < len(data) and data[pos] != 0:
                        pos += data[pos] + 1
                    pos += 1

                if pos + 10 > len(data):
                    break
                rtype, rclass, ttl, rdlength = struct.unpack('!HHIH', data[pos:pos+10])
                pos += 10

                if pos + rdlength > len(data):
                    break

                if rtype == 16:
                    rdata = data[pos:pos+rdlength]
                    txt_data = []
                    offset = 0
                    while offset < len(rdata):
                        slen = rdata[offset]
                        offset += 1
                        if offset + slen <= len(rdata):
                            txt_data.append(rdata[offset:offset+slen].decode('utf-8', errors='ignore'))
                            offset += slen
                    records.append(''.join(txt_data))

                pos += rdlength

        except (struct.error, IndexError):
            pass

        return records


class DnsTxtProtocol(asyncio.DatagramProtocol):
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
