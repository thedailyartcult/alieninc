"""
Plugin 1164: ISO 27001 A.9.1.2 Access to Networks Check
=========================================================
Checks ISO 27001 A.9.1.2 (Access to Networks and Network Services)
by verifying that network access controls are in place.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class Iso27001A912Detection(NaslPlugin):
    PLUGIN_ID = 1164
    NAME = 'ISO 27001 A.9.1.2 Access to Networks Check'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Checks ISO 27001 A.9.1.2 (Access to Networks and Network Services) '
        'by verifying that network access controls are in place. Tests for '
        'segmentation between public-facing services and internal services.'
    )
    SOLUTION = (
        'Implement network segmentation. Use firewalls to restrict access. '
        'Apply principle of least privilege for network access.'
    )
    PORTS = [80, 443, 8080, 8443, 22, 3306, 5432, 6379, 27017]

    INTERNAL_SERVICE_PORTS = [
        (3306, 'MySQL'),
        (5432, 'PostgreSQL'),
        (6379, 'Redis'),
        (27017, 'MongoDB'),
        (11211, 'Memcached'),
        (9200, 'Elasticsearch'),
        (9300, 'Elasticsearch transport'),
        (5672, 'RabbitMQ'),
        (5432, 'PostgreSQL'),
        (8086, 'InfluxDB'),
        (2181, 'ZooKeeper'),
        (9092, 'Kafka'),
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ports_to_check = self.PORTS if port is None else [port]

        for port_to_check in ports_to_check:
            if port_to_check in (80, 443, 8080, 8443):
                try:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE

                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                    )
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'
                    req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                    writer.write(req.encode())
                    await writer.drain()
                    response = b''
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 16384:
                            break
                    writer.close()
                    await writer.wait_closed()

                    header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                    headers = {}
                    for line in header_section.split('\r\n')[1:]:
                        if ':' in line:
                            key, val = line.split(':', 1)
                            headers[key.strip().lower()] = val.strip()

                    server = headers.get('server', '')
                    x_powered = headers.get('x-powered-by', '')
                    internal_indicators = ['internal', 'private', 'corp', 'intranet']

                    body = response.split(b'\r\n\r\n', 1)
                    body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''
                    body_lower = body_text.lower()

                    has_internal_signal = any(ind in body_lower for ind in internal_indicators)

                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'Public web service accessible on port {port_to_check}',
                        evidence=f'Server: {server}, Internal signals: {has_internal_signal}'
                    ))

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Cannot access public web service on port {port_to_check}',
                        solution='Ensure public-facing web services are accessible on standard ports.',
                        evidence=f'Port {port_to_check} unreachable — check firewall/network segmentation rules'
                    ))

            elif any(port_to_check == ip for ip, _ in self.INTERNAL_SERVICE_PORTS):
                service_name = next((name for p, name in self.INTERNAL_SERVICE_PORTS if p == port_to_check), 'Unknown')
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check), timeout=3
                    )
                    banner = b''
                    try:
                        banner = await asyncio.wait_for(reader.read(1024), timeout=2)
                    except asyncio.TimeoutError:
                        pass
                    writer.close()
                    await writer.wait_closed()

                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Internal service ({service_name}) exposed on port {port_to_check}',
                        solution='Restrict access to internal services using network segmentation and firewalls.',
                        evidence=f'{service_name} accessible on port {port_to_check} — should not be publicly reachable',
                        references=[
                            'https://www.iso.org/isoiec-27001-information-security.html',
                            'https://www.tenable.com/plugins/nessus/109343',
                        ]
                    ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'Internal service ({service_name}) not publicly accessible — proper segmentation',
                        evidence=f'Port {port_to_check} filtered/refused — network access control in place'
                    ))

        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
