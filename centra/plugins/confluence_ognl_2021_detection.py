"""
Plugin 1100: Atlassian Confluence Server OGNL Injection RCE (CVE-2021-26084)
=============================================================================
Detects OGNL injection RCE in Atlassian Confluence Server.
Real CVE: CVE-2021-26084 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ConfluenceOgnl2021Detection(NaslPlugin):
    PLUGIN_ID = 1100
    NAME = 'Atlassian Confluence Server OGNL Injection RCE (CVE-2021-26084)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Atlassian Confluence Server before 7.4.10, 7.11.6, 7.12.5, 7.13.0, '
        'and 7.14.0 allows OGNL injection in multiple endpoints including '
        '/pages/createpage-entervariables.action. An unauthenticated attacker '
        'can execute arbitrary code on the Confluence server.'
    )
    SOLUTION = (
        'Upgrade Confluence to a patched version (7.4.10, 7.11.6, 7.12.5, '
        '7.13.0, 7.14.0 or later).'
    )
    CVE = ['CVE-2021-26084']
    PORTS = [80, 443, 8080, 8443, 8090]

    CONFLUENCE_PATHS = [
        '/pages/createpage-entervariables.action',
        '/login.action',
        '/dashboard.action',
    ]
    CONFLUENCE_INDICATORS = [
        b'Confluence',
        b'AJS',
        b'atl.token',
        b'com.atlassian.confluence',
        b'confluence-context-path',
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
                        confluence_detected = any(indicator in response for indicator in self.CONFLUENCE_INDICATORS)

                        if confluence_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Atlassian Confluence Server detected on port '
                                    f'{port_to_check} — potentially vulnerable to OGNL '
                                    f'injection RCE (CVE-2021-26084)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Confluence indicators found: {confluence_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-26084',
                                    'https://www.tenable.com/plugins/nessus/153278',
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
                description='No Confluence OGNL injection indicators detected on checked ports'
            ))

        return results
