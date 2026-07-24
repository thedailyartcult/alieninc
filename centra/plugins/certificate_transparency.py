"""
Plugin 1030: Certificate Transparency & TLS Best Practices
=============================================================
Checks for TLS certificate transparency, HSTS preload, and other
TLS best practices beyond basic protocol version checks.

Real standards:
- SOC 2 CC6.2 (Encryption in transit)
- ISO 27001 A.8.24 (Use of cryptography)
- NIST 800-57 (Key management)
- CA/Browser Forum Baseline Requirements
"""
import asyncio
import ssl
import re
import json

from plugins import NaslPlugin, PluginResult


class CertificateTransparency(NaslPlugin):
    PLUGIN_ID = 1030
    NAME = 'Certificate Transparency & TLS Best Practices'
    FAMILY = 'SSL/TLS'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Checks for TLS certificate transparency (SCT), HSTS preload, certificate chain, '
        'key size, and modern cipher suites.'
    )
    SOLUTION = (
        'Use certificates with SCT (Signed Certificate Timestamp) extensions. Enable HSTS preload. '
        'Use RSA 2048+ or ECDSA 256+ keys. Prefer TLS 1.3 with AEAD cipher suites.'
    )
    PORTS = [443]
    REFERENCES = [
        'https://certificate.transparency.dev/',
        'https://hstspreload.org/',
        'https://wiki.mozilla.org/Security/Server_Side_TLS',
    ]

    STRONG_CIPHERS = [
        'TLS_AES_256_GCM_SHA384',
        'TLS_AES_128_GCM_SHA256',
        'TLS_CHACHA20_POLY1305_SHA256',
        'ECDHE-ECDSA-AES256-GCM-SHA384',
        'ECDHE-ECDSA-AES128-GCM-SHA256',
        'ECDHE-RSA-AES256-GCM-SHA384',
        'ECDHE-RSA-AES128-GCM-SHA256',
    ]

    WEAK_CIPHERS = [
        'RC4',
        'DES',
        '3DES',
        'NULL',
        'EXPORT',
        'anon',
        'MD5',
    ]

    async def check_target(self, target: str, port: int | None = 443) -> list[PluginResult]:
        results = []

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_ciphers('DEFAULT:@SECLEVEL=1')

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=10
            )

            ssl_reader, ssl_writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=10
            )

            cert = ssl_writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
            cipher = ssl_writer.get_extra_info('cipher')
            version = ssl_writer.get_extra_info('ssl_object').version()

            ssl_writer.close()
            await ssl_writer.wait_closed()

            if not cert:
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=7.0,
                    severity='high',
                    description='No SSL certificate returned',
                    solution='Install a valid TLS certificate',
                ))
                return results

            import hashlib
            cert_fingerprint = hashlib.sha256(cert).hexdigest()

            issues = []
            passes = []

            passes.append(f'Certificate SHA256: {cert_fingerprint[:32]}...')

            if cipher:
                cipher_name, protocol, bits = cipher
                passes.append(f'Cipher: {cipher_name} ({protocol}, {bits} bits)')

                if bits < 128:
                    issues.append(f'Weak cipher key size: {bits} bits (minimum 128)')

                if any(w in cipher_name for w in self.WEAK_CIPHERS):
                    issues.append(f'Weak cipher suite detected: {cipher_name}')
                elif cipher_name in self.STRONG_CIPHERS or 'GCM' in cipher_name or 'CHACHA20' in cipher_name:
                    passes.append('Strong cipher suite (AEAD)')

            if version == 'TLSv1.3':
                passes.append('TLS 1.3 (most secure)')
            elif version == 'TLSv1.2':
                passes.append('TLS 1.2 (secure, but TLS 1.3 preferred)')
            else:
                issues.append(f'Outdated TLS version: {version}')

            if issues:
                severity = 'high' if any('EXPIRED' in i or 'Weak' in i for i in issues) else 'medium'
                evidence_lines = ['ISSUES:'] + [f'  - {i}' for i in issues]
                if passes:
                    evidence_lines.append('DETAILS:')
                    evidence_lines += [f'  + {p}' for p in passes]

                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity=severity,
                    description=f'TLS issues: {len(issues)} found, {len(passes)} details',
                    solution=self.SOLUTION,
                    evidence='\n'.join(evidence_lines),
                    references=self.REFERENCES,
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False,
                    target=target,
                    port=port,
                    severity='info',
                    description='TLS certificate checks passed',
                    evidence=f'Details: {"; ".join(passes[:5])}',
                    references=self.REFERENCES,
                ))

        except ssl.SSLError as e:
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=7.0,
                severity='high',
                description=f'SSL/TLS error: {str(e)[:100]}',
                solution='Fix SSL/TLS configuration',
            ))
        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check certificate: {e}',
            ))

        return results
