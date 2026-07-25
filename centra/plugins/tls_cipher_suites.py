"""
Plugin 1158: TLS Cipher Suite Strength Audit
==============================================
Audits TLS cipher suites offered by the server, detecting weak ciphers.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class TlsCipherSuites(NaslPlugin):
    PLUGIN_ID = 1158
    NAME = 'TLS Cipher Suite Strength Audit'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Audits the TLS cipher suites offered by the server, detecting weak '
        'ciphers (RC4, DES, 3DES), export-grade ciphers, and missing forward '
        'secrecy. Weak ciphers can be broken by attackers to decrypt TLS traffic.'
    )
    SOLUTION = (
        'Disable weak cipher suites. Prioritize AEAD ciphers (AES-GCM, '
        'ChaCha20-Poly1305). Require forward secrecy (ECDHE/DHE).'
    )
    PORTS = [443, 8443]

    WEAK_CIPHER_PATTERNS = [
        'rc4', 'des', '3des', 'idea', 'seed', 'export',
    ]
    WEAK_CIPHER_NAMES = [
        'TLS_RSA_WITH_RC4_128_MD5',
        'TLS_RSA_WITH_RC4_128_SHA',
        'TLS_RSA_WITH_3DES_EDE_CBC_SHA',
        'TLS_RSA_WITH_DES_CBC_SHA',
        'TLS_DH_anon_WITH_AES_128_GCM_SHA256',
        'TLS_DH_anon_WITH_AES_256_GCM_SHA384',
        'TLS_ECDH_anon_WITH_AES_128_CBC_SHA',
        'TLS_ECDH_anon_WITH_AES_256_CBC_SHA',
    ]
    NO_FS_CIPHERS = [
        'TLS_RSA_WITH_AES_128_GCM_SHA256',
        'TLS_RSA_WITH_AES_256_GCM_SHA384',
        'TLS_RSA_WITH_AES_128_CBC_SHA',
        'TLS_RSA_WITH_AES_256_CBC_SHA',
    ]

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
                cipher = writer.get_extra_info('cipher', {})
                peercert = writer.get_extra_info('peercert')
                writer.close()
                await writer.wait_closed()

                cipher_name = cipher.get('name', '') if cipher else ''
                cipher_ver = cipher.get('version', '') if cipher else ''

                weak_found = []
                no_fs_found = []
                cipher_lower = cipher_name.lower()

                for weak in self.WEAK_CIPHER_PATTERNS:
                    if weak in cipher_lower:
                        weak_found.append(cipher_name)
                        break

                if cipher_name in self.WEAK_CIPHER_NAMES:
                    if cipher_name not in weak_found:
                        weak_found.append(cipher_name)

                if cipher_name in self.NO_FS_CIPHERS:
                    no_fs_found.append(cipher_name)

                if weak_found:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Weak cipher suite accepted: {", ".join(weak_found)}',
                        solution=self.SOLUTION,
                        evidence=f'Cipher: {cipher_name}, Version: {cipher_ver}',
                        references=[
                            'https://www.tenable.com/plugins/nessus/108093',
                            'https://www.owasp.org/index.php/TLS_Cheat_Sheet',
                        ]
                    ))
                elif no_fs_found:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=5.9, severity='medium',
                        description=f'Cipher suite lacks forward secrecy: {", ".join(no_fs_found)}',
                        solution='Prioritize cipher suites with ECDHE or DHE key exchange.',
                        evidence=f'Cipher: {cipher_name}',
                        references=['https://www.tenable.com/plugins/nessus/108093']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'Cipher suite appears strong: {cipher_name}',
                        evidence=f'Cipher: {cipher_name}, Version: {cipher_ver}'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
