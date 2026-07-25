"""
Plugin 1152: DNS CAA Record Check
====================================
Checks for DNS CAA (Certificate Authority Authorization) records.
"""
import asyncio
import re
import struct

from plugins import NaslPlugin, PluginResult


class CaaRecordDetection(NaslPlugin):
    PLUGIN_ID = 1152
    NAME = 'DNS CAA Record Check'
    FAMILY = 'DNS'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Checks for DNS CAA (Certificate Authority Authorization) records that '
        'specify which Certificate Authorities are allowed to issue SSL/TLS '
        'certificates for the domain. Missing CAA records allow any CA to issue '
        'certificates for the domain.'
    )
    SOLUTION = (
        'Publish CAA records restricting certificate issuance to authorized CAs '
        '(e.g., letsencrypt.org, digicert.com).'
    )
    CVE = []
    PORTS = [53]

    async def check_target(self, target: str, port: int | None = 53) -> list[PluginResult]:
        port = port or 53

        domain = target
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', target):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Target is an IP address, CAA records not applicable')]

        try:
            query = self._build_caa_query(domain)

            loop = asyncio.get_running_loop()
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: DnsCaaProtocol(), local_addr=('0.0.0.0', 0)
                ), timeout=3
            )

            protocol.transport.sendto(query, (target, port))
            data = await asyncio.wait_for(protocol.future, timeout=5)
            transport.close()

            if data and len(data) > 12:
                caa_records = self._parse_caa_records(data)
                if caa_records:
                    caa_details = []
                    for tag, value in caa_records:
                        caa_details.append(f'{tag}={value}')

                    return [PluginResult(
                        vulnerable=False, target=target, port=port,
                        cvss_score=0.0, severity='info',
                        description=f'CAA records found: {len(caa_records)} record(s) configured',
                        solution=self.SOLUTION,
                        evidence='; '.join(caa_details),
                        references=[
                            'https://datatracker.ietf.org/doc/html/rfc6844',
                            'https://letsencrypt.org/docs/caa/',
                        ]
                    )]
                else:
                    rcode = struct.unpack('!H', data[2:4])[0] & 0x0F
                    if rcode == 0:
                        return [PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description='No CAA record found for domain - any CA can issue certificates',
                            solution=self.SOLUTION,
                            evidence='DNS response indicates no CAA records (empty answer section)',
                            references=[
                                'https://datatracker.ietf.org/doc/html/rfc6844',
                                'https://letsencrypt.org/docs/caa/',
                            ]
                        )]

        except (asyncio.TimeoutError, OSError):
            pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='Could not query CAA records (DNS server not reachable)'
        )]

    def _build_caa_query(self, domain: str) -> bytes:
        header = struct.pack('!HHHHHH', 0x1234, 0x0100, 1, 0, 0, 0)
        qname = b''
        for label in domain.strip('.').split('.'):
            qname += bytes([len(label)]) + label.encode()
        qname += b'\x00'
        qtype_caa = struct.pack('!HH', 257, 1)
        return header + qname + qtype_caa

    def _parse_caa_records(self, data: bytes) -> list[tuple[str, str]]:
        records = []
        try:
            pos = 12
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

                if rtype == 257:
                    if pos + 2 <= len(data):
                        flags = data[pos]
                        tag_length = data[pos + 1]
                        pos += 2
                        if pos + tag_length + rdlength - 2 - tag_length <= len(data):
                            tag = data[pos:pos+tag_length].decode('utf-8', errors='ignore')
                            pos += tag_length
                            value = data[pos:pos+rdlength - 2 - tag_length].decode('utf-8', errors='ignore')
                            records.append((tag, value))
                            pos += rdlength - 2 - tag_length
                        else:
                            pos += rdlength - 2
                    else:
                        pos += rdlength
                else:
                    pos += rdlength

        except (struct.error, IndexError):
            pass

        return records


class DnsCaaProtocol(asyncio.DatagramProtocol):
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
