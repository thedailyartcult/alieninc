import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class TlsRenegotiation(NaslPlugin):
    PLUGIN_ID = 1247
    NAME = 'TLS Renegotiation Denial of Service Detection'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects TLS renegotiation enabled on the server, which can be abused for denial of service by repeatedly requesting renegotiation, consuming CPU resources. Also checks for client-initiated renegotiation which was the basis for the SSL Renegotiation DoS attack.'
    SOLUTION = 'Disable TLS renegotiation if not required. Set limits on renegotiation frequency. Use modern TLS 1.3 which handles renegotiation differently.'
    CVE = ['CVE-2011-1473']
    PORTS = [443, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                ssl_obj = writer.get_extra_info('ssl_object')
                version = ssl_obj.version()
                reneg = False
                if version not in ('TLSv1.3', 'TLSv1.3+', None):
                    try:
                        loop = asyncio.get_running_loop()
                        await asyncio.wait_for(loop.run_in_executor(None, ssl_obj.do_handshake), timeout=3)
                        reneg = True
                    except (ssl.SSLError, ValueError, RuntimeError, asyncio.TimeoutError):
                        pass
                writer.close()
                await writer.wait_closed()
                if reneg:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'TLS renegotiation supported ({version}). Vulnerable to CVE-2011-1473 renegotiation DoS.'))
                else:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'TLS renegotiation not supported or restricted ({version})'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError) as e:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'Connection failed: {e}'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
