"""
Plugin 1159: TLS Protocol Version Security Check
==================================================
Checks for support of deprecated TLS protocol versions.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class TlsProtocolVersions(NaslPlugin):
    PLUGIN_ID = 1159
    NAME = 'TLS Protocol Version Security Check'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Checks for support of deprecated TLS protocol versions (TLS 1.0, TLS 1.1) '
        'that are known to be vulnerable to protocol downgrade attacks, POODLE, '
        'BEAST, and other cryptographic attacks. Only TLS 1.2 and TLS 1.3 are '
        'considered secure.'
    )
    SOLUTION = (
        'Disable TLS 1.0 and TLS 1.1. Enable TLS 1.2 and TLS 1.3 only.'
    )
    PORTS = [443, 8443]

    DEPRECATED_PROTOCOLS = [
        ('TLSv1.0', ssl.TLSVersion.TLSv1),
        ('TLSv1.1', ssl.TLSVersion.TLSv1_1),
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            deprecated_found = []

            for proto_name, proto_ver in self.DEPRECATED_PROTOCOLS:
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    ctx.minimum_version = proto_ver
                    ctx.maximum_version = proto_ver

                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                    )
                    writer.close()
                    await writer.wait_closed()

                    deprecated_found.append(proto_name)
                except (ssl.SSLError, asyncio.TimeoutError, ConnectionResetError, OSError):
                    pass

            if deprecated_found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=port_to_check,
                    cvss_score=self.CVSS_SCORE, severity='high',
                    description=f'Server accepts deprecated TLS versions: {", ".join(deprecated_found)}',
                    solution=self.SOLUTION,
                    evidence=f'Deprecated protocols accepted on port {port_to_check}: {", ".join(deprecated_found)}',
                    references=[
                        'https://www.tenable.com/plugins/nessus/104708',
                        'https://www.owasp.org/index.php/TLS_Cheat_Sheet',
                    ]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No deprecated TLS protocols accepted',
                    evidence=f'Port {port_to_check} does not accept TLS 1.0 or TLS 1.1'
                ))

        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
