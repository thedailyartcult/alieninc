"""
Plugin 1108: Microsoft Exchange ProxyNotShell SSRF (CVE-2022-41040)
====================================================================
Detects CVE-2022-41040 SSRF in Microsoft Exchange Server.
Real CVE: CVE-2022-41040 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ProxynotshellSsrfDetection(NaslPlugin):
    PLUGIN_ID = 1108
    NAME = 'Microsoft Exchange ProxyNotShell SSRF (CVE-2022-41040)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Microsoft Exchange Server 2016 and 2019 before November 2022 updates contain '
        'a server-side request forgery (SSRF) vulnerability in the Exchange Server '
        'PowerShell backend. An authenticated attacker can use this SSRF to relay '
        'requests to internal services. When chained with CVE-2022-41082, unauthenticated '
        'RCE is possible (ProxyNotShell chain).'
    )
    SOLUTION = (
        'Apply Microsoft November 2022 security updates. Disable Exchange PowerShell '
        'backend external access.'
    )
    CVE = ['CVE-2022-41040']
    PORTS = [443, 80, 8080, 8443]

    EXCHANGE_PATHS = [
        '/autodiscover/autodiscover.json?@evil.com/mapi/nspi/',
        '/autodiscover/autodiscover.xml',
        '/ecp/',
        '/owa/',
        '/powershell/',
    ]

    EXCHANGE_HEADERS = [
        b'X-FEServer',
        b'X-CalculatedBETarget',
        b'X-DiagInfo',
        b'X-OWA-Version',
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

                        exchange_detected = any(h in response for h in self.EXCHANGE_HEADERS)
                        is_200 = b'200' in response[:50]
                        is_404 = b'404' in response[:50]

                        if exchange_detected or (is_200 and b'Autodiscover' in response):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Microsoft Exchange Server detected on port {port_to_check} — '
                                    f'ProxyNotShell SSRF (CVE-2022-41040) may be exploitable'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Exchange headers: {exchange_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-41040',
                                    'https://msrc.microsoft.com/update-guide/vulnerability/CVE-2022-41040',
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
                description='No Exchange or ProxyNotShell SSRF indicators detected'
            ))

        return results
