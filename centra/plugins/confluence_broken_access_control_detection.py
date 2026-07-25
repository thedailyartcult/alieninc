"""
Plugin 1106: Atlassian Confluence Broken Access Control (CVE-2023-22515)
=========================================================================
Detects CVE-2023-22515 broken access control in Confluence Data Center/Server.
Real CVE: CVE-2023-22515 (CVSS 10.0)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ConfluenceBrokenAccessControlDetection(NaslPlugin):
    PLUGIN_ID = 1106
    NAME = 'Atlassian Confluence Broken Access Control (CVE-2023-22515)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 10.0
    CVSS = 10.0
    DESCRIPTION = (
        'Atlassian Confluence Data Center and Server 8.0.0 through 8.5.1 contains '
        'a broken access control vulnerability. An unauthenticated attacker can exploit '
        'the /server-info.action endpoint to modify application configuration, bypass '
        'setup completion, and create unauthorized administrator accounts. Actively '
        'exploited by nation-state threat actors. Atlassian rates this as CVSS 10.0.'
    )
    SOLUTION = (
        'Upgrade Confluence to 8.3.3, 8.4.3, 8.5.2 or later. Restrict network access '
        'to Confluence. Check for unauthorized admin accounts.'
    )
    CVE = ['CVE-2023-22515']
    PORTS = [80, 443, 8080, 8443, 8090]

    CONFLUENCE_PATHS = [
        '/server-info.action?bootstrapStatusProvider.applicationConfig.setupComplete=false',
        '/login.action',
        '/',
    ]

    CONFLUENCE_HINTS = [
        b'Confluence',
        b'Atlassian',
        b'setupComplete',
        b'applicationConfig',
        b'com.atlassian',
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

                for path in self.CONFLUENCE_PATHS:
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
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')

                        is_200 = b'200' in response[:50]
                        confluence_hits = [h for h in self.CONFLUENCE_HINTS if h in response]
                        setup_complete_reflected = b'setupComplete' in response or b'setup-complete' in response

                        if confluence_hits or (is_200 and b'Confluence' in response):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Atlassian Confluence detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2023-22515 broken access control'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Confluence indicators: {confluence_hits}, '
                                    f'SetupComplete reflected: {setup_complete_reflected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-22515',
                                    'https://confluence.atlassian.com/security/cve-2023-22515.html',
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
                description='No Atlassian Confluence or CVE-2023-22515 indicators detected'
            ))

        return results
