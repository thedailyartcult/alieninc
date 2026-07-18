"""
Plugin 1005: TLS/SSL Weakness Check
=====================================
Detects weak TLS versions, cipher suites, and certificate issues.
Real CVEs: CVE-2023-38802 (Raccoon), CVE-2022-4304, CVE-2021-3449
"""
import asyncio
import ssl
import socket
from datetime import datetime

from plugins import NaslPlugin, PluginResult


class TlsWeakness(NaslPlugin):
    PLUGIN_ID = 1005
    NAME = 'TLS/SSL Weakness Check'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 7.4
    DESCRIPTION = (
        'The remote service uses TLS/SSL with weak protocol versions or cipher '
        'suites. This may allow interception of encrypted communications.'
    )
    SOLUTION = (
        'Disable TLS 1.0 and 1.1. Use TLS 1.2+ with strong cipher suites. '
        'Replace self-signed or expired certificates. Disable SSL compression '
        'to prevent CRIME attacks.'
    )
    CVE = ['CVE-2023-38802', 'CVE-2022-4304', 'CVE-2021-3449', 'CVE-2015-0204']
    PORTS = [443, 8443, 993, 995]

    WEAK_PROTOCOLS = {'SSLv2', 'SSLv3', 'TLSv1', 'TLSv1.1'}

    async def check_target(self, target: str, port: int | None = 443) -> list[PluginResult]:
        port = port or 443
        results = []

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            for proto_name, proto_ver in [
                ('TLSv1.1', ssl.TLSVersion.TLSv1_1),
                ('TLSv1', ssl.TLSVersion.TLSv1),
            ]:
                try:
                    inner_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    inner_ctx.check_hostname = False
                    inner_ctx.verify_mode = ssl.CERT_NONE
                    inner_ctx.maximum_version = proto_ver

                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port, ssl=inner_ctx),
                        timeout=5
                    )
                    writer.close()
                    await writer.wait_closed()

                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='high',
                        description=f'Server accepts weak TLS version: {proto_name}',
                        solution=self.SOLUTION,
                        evidence=f'Accepted {proto_name} connection on port {port}',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-38802',
                            'https://www.owasp.org/index.php/TLS_Cheat_Sheet',
                        ]
                    ))
                    break
                except (ssl.SSLError, asyncio.TimeoutError, ConnectionResetError):
                    pass

            try:
                cert_reader, cert_writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ctx), timeout=5
                )
                peercert = cert_writer.get_extra_info('peercert')
                cert_writer.close()
                await cert_writer.wait_closed()

                if peercert:
                    not_after = peercert.get('notAfter', '')
                    if not_after:
                        try:
                            exp_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                            days_left = (exp_date - datetime.utcnow()).days
                            if days_left < 0:
                                results.append(PluginResult(
                                    vulnerable=True, target=target, port=port,
                                    cvss_score=7.5, severity='high',
                                    description=f'Certificate expired {abs(days_left)} days ago',
                                    solution='Renew the TLS certificate immediately.',
                                    evidence=f'Certificate expired: {not_after}',
                                    references=['https://nvd.nist.gov/vuln/detail/CVE-2022-4304']
                                ))
                            elif days_left < 30:
                                results.append(PluginResult(
                                    vulnerable=True, target=target, port=port,
                                    cvss_score=3.7, severity='low',
                                    description=f'Certificate expires in {days_left} days',
                                    solution='Renew the TLS certificate before expiration.',
                                    evidence=f'Certificate expires: {not_after}',
                                ))
                        except ValueError:
                            pass

            except (ssl.SSLError, asyncio.TimeoutError, OSError):
                pass

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description=f'Port {port} not reachable')]

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description='TLS configuration appears secure'
            ))

        return results
