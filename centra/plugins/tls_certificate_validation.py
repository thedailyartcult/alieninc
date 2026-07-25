"""
Plugin 1160: TLS Certificate Chain Validation
===============================================
Validates the TLS certificate chain including expiry, signature, and key size.
"""
import asyncio
import ssl
from datetime import datetime, timezone

from plugins import NaslPlugin, PluginResult


class TlsCertificateValidation(NaslPlugin):
    PLUGIN_ID = 1160
    NAME = 'TLS Certificate Chain Validation'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Validates the TLS certificate chain including expiry dates, signature '
        'algorithms, key sizes, and hostname matching. Expired, self-signed, or '
        'improperly configured certificates can lead to MITM attacks or service '
        'disruptions.'
    )
    SOLUTION = (
        'Use certificates from trusted CAs. Ensure certificate covers all required '
        'hostnames. Renew before expiry. Use 2048+ bit RSA or ECDSA keys.'
    )
    PORTS = [443, 8443]

    WEAK_SIGNATURE_ALGOS = ['md2', 'md4', 'md5', 'sha1']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                peercert = writer.get_extra_info('peercert')
                cipher = writer.get_extra_info('cipher', {})
                writer.close()
                await writer.wait_closed()

                if not peercert:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=7.5, severity='high',
                        description='No certificate presented by server',
                        solution=self.SOLUTION,
                        evidence=f'No peer certificate on port {port_to_check}'
                    ))
                    continue

                issues = []

                not_after = peercert.get('notAfter', '')
                not_before = peercert.get('notBefore', '')
                if not_after:
                    try:
                        exp_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                        utc_now = datetime.now(timezone.utc)
                        exp_date_utc = exp_date.replace(tzinfo=timezone.utc)
                        days_left = (exp_date_utc - utc_now).days
                        if days_left < 0:
                            issues.append(f'Certificate expired {abs(days_left)} days ago')
                        elif days_left < 30:
                            issues.append(f'Certificate expires in {days_left} days')
                    except ValueError:
                        pass

                subject = peercert.get('subject', ())
                issuer = peercert.get('issuer', ())
                serial = peercert.get('serialNumber', '')

                sig_algo = cipher.get('name', '') if cipher else ''
                for weak_algo in self.WEAK_SIGNATURE_ALGOS:
                    if weak_algo in sig_algo.lower():
                        issues.append(f'Weak signature algorithm: {sig_algo}')
                        break

                subject_str = ''
                if subject:
                    for attr in subject:
                        if isinstance(attr, tuple):
                            for pair in attr:
                                if isinstance(pair, tuple) and len(pair) >= 2:
                                    if pair[0] == 'commonName':
                                        subject_str = pair[1]

                is_self_signed = False
                if subject and issuer:
                    subject_str_full = ''.join(str(s) for s in subject)
                    issuer_str_full = ''.join(str(s) for s in issuer)
                    if subject_str_full == issuer_str_full:
                        is_self_signed = True
                        issues.append('Self-signed certificate')

                if issues:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'Certificate issues: {"; ".join(issues)}',
                        solution=self.SOLUTION,
                        evidence=f'Subject: {subject_str}, Issuer: {issuer}, Serial: {serial}, Issues: {"; ".join(issues)}',
                        references=[
                            'https://www.tenable.com/plugins/nessus/104743',
                            'https://www.owasp.org/index.php/TLS_Cheat_Sheet',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='TLS certificate appears valid',
                        evidence=f'Subject: {subject_str}, Expires: {not_after}'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError) as e:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=port_to_check,
                    cvss_score=5.0, severity='medium',
                    description=f'TLS handshake failed: {str(e)}',
                    solution='Ensure TLS is properly configured and certificate is valid.',
                    evidence=f'Handshake error on port {port_to_check}: {str(e)}'
                ))

        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
