"""
Plugin 1076: ProxyShell — Microsoft Exchange RCE (ProxyShell chain)
====================================================================
Detects ProxyShell attack chain on Microsoft Exchange Server.
Real CVEs: CVE-2021-34473 (CVSS 9.1), CVE-2021-34523 (CVSS 9.8),
CVE-2021-31207 (CVSS 7.5) — chained: CVSS 9.8
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ProxyshellDetection(NaslPlugin):
    PLUGIN_ID = 1076
    NAME = 'Microsoft Exchange ProxyShell RCE Detection'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'ProxyShell is an attack chain targeting on-premises Microsoft Exchange '
        'Server. CVE-2021-34473 is a pre-auth SSRF that allows access to Exchange '
        'backend services. CVE-2021-34523 is an Exchange PowerShell backend elevation '
        'of privilege. CVE-2021-31207 is a post-auth arbitrary file write. Chained '
        'together, an unauthenticated attacker can achieve remote code execution on '
        'Exchange servers.'
    )
    SOLUTION = (
        'Apply Microsoft security updates from July 2021 or later. Block external '
        'access to Exchange backend paths (/autodiscover/, /ecp/, /owa/, /powershell/). '
        'Monitor for suspicious autodiscover requests.'
    )
    CVE = ['CVE-2021-34473', 'CVE-2021-34523', 'CVE-2021-31207']
    PORTS = [443, 80, 8080]

    EXCHANGE_PATHS = [
        '/autodiscover/autodiscover.json?@evil.com/mapi/nspi/',
        '/autodiscover/autodiscover.xml',
        '/owa/',
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
                        is_404 = b'404' in response[:50] or b'404 Not Found' in response[:100]
                        is_200 = b'200 OK' in response[:50]

                        if exchange_detected or (is_200 and b'Autodiscover' in response):
                            nspi_hint = '/mapi/nspi' in path
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Microsoft Exchange Server detected on port {port_to_check} — '
                                    f'ProxyShell attack chain may be exploitable'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'NSPI probe: {"accessible" if nspi_hint and not is_404 else "blocked"}, '
                                    f'Exchange headers: {exchange_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-34473',
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-34523',
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-31207',
                                    'https://www.tenable.com/plugins/nessus/152698',
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
                description='No ProxyShell or Exchange indicators detected on checked ports'
            ))

        return results
