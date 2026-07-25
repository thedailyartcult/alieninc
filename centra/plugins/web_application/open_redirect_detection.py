"""
Plugin 1043: Open Redirect Detection
=======================================
Detects URL parameters that result in redirect to attacker-controlled domains.
Real CVEs: CVE-2024-22113 (open redirect), CVE-2023-38574 (open redirect)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class OpenRedirectDetection(NaslPlugin):
    PLUGIN_ID = 1043
    NAME = 'Open Redirect Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 4.3
    DESCRIPTION = (
        'The web application contains open redirect parameters. An attacker '
        'can exploit these to redirect users to malicious sites, enabling '
        'phishing attacks and bypassing URL validation controls.'
    )
    SOLUTION = (
        'Validate and whitelist redirect parameters. Do not allow redirects '
        'to external domains without a target whitelist. Use relative URLs only.'
    )
    CVE = ['CVE-2024-22113', 'CVE-2023-38574']
    PORTS = [80, 443]

    REDIRECT_PARAMS = [
        'redirect', 'url', 'next', 'return', 'return_to', 'return_url',
        'r', 'u', 'target', 'goto', 'link', 'location', 'dest',
        'destination', 'out', 'view', 'dir', 'to',
    ]

    TEST_DOMAIN = 'evil-attacker.example.com/phish'

    REDIRECT_PATHS = [
        '/redirect', '/go', '/link', '/out', '/forward', '/proxy',
        '/external', '/leave', '/away', '/outgoing', '/track',
        '/click', '/safelink', '/exit', '/r', '/to', '/l',
    ]

    async def _fetch_and_check(self, target: str, port: int, path: str,
                                param: str) -> PluginResult | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            test_url = f'{path}?{param}={self.TEST_DOMAIN}'
            req = f'GET {test_url} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()
            tresp = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                tresp += chunk
                if len(tresp) > 8192:
                    break
            writer.close()
            await writer.wait_closed()

            resp_headers = tresp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            if 'location:' in resp_headers:
                for hline in resp_headers.split('\r\n'):
                    if hline.startswith('location:'):
                        loc = hline.split(':', 1)[1].strip()
                        if 'evil-attacker' in loc:
                            return PluginResult(
                                vulnerable=True, target=target, port=port,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'Open redirect via param "{param}" on {path}',
                                solution=self.SOLUTION,
                                evidence=f'{path}?{param}={self.TEST_DOMAIN} -> Location: {loc}',
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2024-22113',
                                    'https://www.tenable.com/plugins/nessus/112004',
                                ]
                            )
            return None
        except Exception:
            return None

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80

        paths_to_probe = ['/'] + self.REDIRECT_PATHS
        for path in paths_to_probe:
            for param in self.REDIRECT_PARAMS[:5]:
                result = await self._fetch_and_check(target, port, path, param)
                if result:
                    return [result]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No open redirect parameters detected'
        )]
