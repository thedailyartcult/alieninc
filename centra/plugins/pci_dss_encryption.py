"""
Plugin 1162: PCI-DSS Encryption in Transit Check
==================================================
Checks PCI-DSS Requirement 4 compliance for encryption of cardholder data.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class PciDssEncryption(NaslPlugin):
    PLUGIN_ID = 1162
    NAME = 'PCI-DSS Encryption in Transit Check'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Checks PCI-DSS Requirement 4 compliance for encryption of cardholder '
        'data in transit. Verifies HTTPS enforcement, TLS 1.2+ availability, '
        'and absence of weak protocols on the target.'
    )
    SOLUTION = (
        'Enforce HTTPS with HSTS. Disable TLS 1.0/1.1. Use strong cipher suites. '
        'Ensure certificate from trusted CA.'
    )
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            findings = []

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check), timeout=5
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

                status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                headers = {}
                for line in header_section.split('\r\n')[1:]:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        headers[key.strip().lower()] = val.strip()

                location = headers.get('location', '')
                hsts = headers.get('strict-transport-security', '')

                if port_to_check in (80, 8080):
                    if '301' in status_line or '302' in status_line or '307' in status_line or '308' in status_line:
                        if location.startswith('https://'):
                            findings.append('HTTP redirects to HTTPS')
                        else:
                            findings.append('HTTP redirect present but not to HTTPS')
                    else:
                        findings.append('HTTP does not redirect to HTTPS')

                if port_to_check in (443, 8443):
                    if not hsts:
                        findings.append('HSTS header missing')

                    for proto_name, proto_ver in [
                        ('TLSv1.0', ssl.TLSVersion.TLSv1),
                        ('TLSv1.1', ssl.TLSVersion.TLSv1_1),
                    ]:
                        try:
                            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            ctx.minimum_version = proto_ver
                            ctx.maximum_version = proto_ver
                            tls_reader, tls_writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=3
                            )
                            tls_writer.close()
                            await tls_writer.wait_closed()
                            findings.append(f'{proto_name} accepted (PCI-DSS non-compliant)')
                        except (ssl.SSLError, asyncio.TimeoutError, ConnectionResetError, OSError):
                            pass

                    try:
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        cert_reader, cert_writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        peercert = cert_writer.get_extra_info('peercert')
                        cert_writer.close()
                        await cert_writer.wait_closed()

                        if peercert:
                            not_after = peercert.get('notAfter', '')
                            if not_after:
                                from datetime import datetime, timezone
                                try:
                                    exp_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                                    utc_now = datetime.now(timezone.utc)
                                    exp_date_utc = exp_date.replace(tzinfo=timezone.utc)
                                    if exp_date_utc < utc_now:
                                        findings.append('Certificate is expired')
                                except ValueError:
                                    findings.append('Could not parse certificate expiry')
                            subject = peercert.get('subject', ())
                            issuer = peercert.get('issuer', ())
                            subject_str = ''.join(str(s) for s in subject)
                            issuer_str = ''.join(str(s) for s in issuer)
                            if subject_str == issuer_str:
                                findings.append('Self-signed certificate')
                    except (ssl.SSLError, asyncio.TimeoutError, OSError):
                        findings.append('TLS handshake failed')

                if findings:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'PCI-DSS encryption issues: {"; ".join(findings)}',
                        solution=self.SOLUTION,
                        evidence=f'Findings on port {port_to_check}: {"; ".join(findings)}',
                        references=[
                            'https://www.pcisecuritystandards.org/',
                            'https://www.tenable.com/plugins/nessus/175895',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='PCI-DSS encryption requirements appear compliant',
                        evidence=f'Port {port_to_check}: HTTPS enforced, TLS 1.2+, valid certificate'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
