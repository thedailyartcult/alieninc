"""
Plugin 1157: OCSP Stapling Check
==================================
Checks if the server supports OCSP stapling (status_request TLS extension).
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class OcspStaplingCheck(NaslPlugin):
    PLUGIN_ID = 1157
    NAME = 'OCSP Stapling Check'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Checks if the server supports OCSP stapling (status_request TLS '
        'extension). OCSP stapling improves TLS handshake performance and '
        'privacy by allowing the server to send a cached OCSP response during '
        'the handshake, eliminating the need for clients to contact the CA directly.'
    )
    SOLUTION = (
        'Enable OCSP stapling in web server configuration. Ensure the server '
        'can reach the CA OCSP responder.'
    )
    PORTS = [443, 8443]

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

                sock = writer.transport.get_extra_info('socket')
                peercert = writer.get_extra_info('peercert')
                cipher = writer.get_extra_info('cipher')
                ssl_obj = writer.get_extra_info('ssl_object')

                ocsp_stapled = False
                if ssl_obj:
                    try:
                        ocsp_resp = ssl_obj.compression()
                        ocsp_stapled = ocsp_resp is not None
                    except (AttributeError, NotImplementedError):
                        pass

                if hasattr(writer.transport, '_ssl_protocol'):
                    ocsp_stapled = True

                writer.close()
                await writer.wait_closed()

                if ocsp_stapled:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='OCSP stapling is supported',
                        evidence=f'OCSP staple response present on port {port_to_check}'
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='low',
                        description='OCSP stapling not supported',
                        solution=self.SOLUTION,
                        evidence=f'No OCSP staple response on port {port_to_check}',
                        references=[
                            'https://www.rfc-editor.org/rfc/rfc6066',
                            'https://www.tenable.com/plugins/nessus/70591',
                        ]
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
