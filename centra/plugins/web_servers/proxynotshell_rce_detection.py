"""
Plugin 1109: Microsoft Exchange ProxyNotShell RCE (CVE-2022-41082)
===================================================================
Detects CVE-2022-41082 RCE in Microsoft Exchange Server.
Real CVE: CVE-2022-41082 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ProxynotshellRceDetection(NaslPlugin):
    PLUGIN_ID = 1109
    NAME = 'Microsoft Exchange ProxyNotShell RCE (CVE-2022-41082)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Microsoft Exchange Server 2016 and 2019 before November 2022 updates contain '
        'a remote code execution vulnerability in PowerShell remoting. When chained with '
        'CVE-2022-41040 (ProxyNotShell SSRF), an unauthenticated attacker can execute '
        'arbitrary commands on the Exchange server.'
    )
    SOLUTION = (
        'Apply Microsoft November 2022 security updates. Disable PowerShell remoting '
        'external access.'
    )
    CVE = ['CVE-2022-41082']
    PORTS = [443, 80, 8080, 8443]

    EXCHANGE_PATHS = [
        '/ecp/',
        '/owa/',
        '/powershell/',
        '/autodiscover/autodiscover.xml',
    ]

    EXCHANGE_HEADERS = [
        b'X-FEServer',
        b'X-CalculatedBETarget',
        b'X-DiagInfo',
        b'X-OWA-Version',
        b'X-Powered-By',
    ]

    POWERSHELL_HINTS = [
        b'PowerShell',
        b'powershell',
        b'PSClient',
        b'winrm',
    ]

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

                for path in self.EXCHANGE_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
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

                    if response:
                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        headers_end = response.find(b'\r\n\r\n')
                        raw_headers = response[:headers_end].decode('utf-8', errors='ignore')

                        exchange_headers_found = any(h in response for h in self.EXCHANGE_HEADERS)
                        powershell_hints_found = [h for h in self.POWERSHELL_HINTS if h in response]
                        is_200 = b'200' in response[:50]
                        is_401 = b'401' in response[:50]
                        is_302 = b'302' in response[:50]

                        if exchange_headers_found or powershell_hints_found or (is_200 and b'Exchange' in response):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Microsoft Exchange detected on port {port_to_check} — '
                                    f'ProxyNotShell RCE (CVE-2022-41082) may be exploitable '
                                    f'when chained with CVE-2022-41040 SSRF'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Exchange headers: {exchange_headers_found}, '
                                    f'PowerShell hints: {powershell_hints_found}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-41082',
                                    'https://msrc.microsoft.com/update-guide/vulnerability/CVE-2022-41082',
                                ]
                            ))
                            break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Exchange or ProxyNotShell RCE indicators detected'
            ))

        return results
