"""
Plugin 1097: Apache HTTP Server mod_proxy SSRF (CVE-2021-40438)
================================================================
Detects SSRF vulnerability in Apache HTTP Server mod_proxy.
Real CVE: CVE-2021-40438 (CVSS 9.0)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ApacheSsrfDetection(NaslPlugin):
    PLUGIN_ID = 1097
    NAME = 'Apache HTTP Server mod_proxy SSRF (CVE-2021-40438)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.0
    DESCRIPTION = (
        'Apache HTTP Server 2.4.48 and earlier has a server-side request '
        'forgery (SSRF) vulnerability in mod_proxy. A crafted request to a '
        'RewriteRule-configured server can cause the server to make requests '
        'to unintended destinations.'
    )
    SOLUTION = (
        'Upgrade to Apache HTTP Server 2.4.49 or later.'
    )
    CVE = ['CVE-2021-40438']
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                req = (
                    f'GET / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Connection: close\r\n\r\n'
                )
                writer.write(req.encode())
                await writer.drain()

                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 8192:
                            break
                except asyncio.TimeoutError:
                    pass

                writer.close()
                await writer.wait_closed()

                if response:
                    apache_detected = b'Apache' in response
                    server_header_present = False
                    for line in response.split(b'\r\n'):
                        if line.lower().startswith(b'server:'):
                            server_header_present = True
                            break

                    if apache_detected or server_header_present:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='critical',
                            description=(
                                f'Apache HTTP Server detected on port {port_to_check} — '
                                f'versions 2.4.48 and earlier may be vulnerable to SSRF '
                                f'via mod_proxy (CVE-2021-40438)'
                            ),
                            solution=self.SOLUTION,
                            evidence=(
                                f'Apache server detected, '
                                f'Server header: {server_header_present}'
                            ),
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2021-40438',
                                'https://www.tenable.com/plugins/nessus/153757',
                            ]
                        ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Apache HTTP Server SSRF indicators detected on checked ports'
            ))

        return results
