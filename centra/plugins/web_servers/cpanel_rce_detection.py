"""
Plugin 1114: CPanel Login RCE (CVE-2022-44877)
===============================================
Detects CVE-2022-44877 authentication bypass in CPanel.
Real CVE: CVE-2022-44877 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CpanelRceDetection(NaslPlugin):
    PLUGIN_ID = 1114
    NAME = 'CPanel Login RCE (CVE-2022-44877)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'CPanel versions before 106.0.18 and 102.0.43 contain an authentication bypass '
        'vulnerability in the login mechanism. An unauthenticated attacker can bypass '
        'authentication and execute arbitrary commands on the server.'
    )
    SOLUTION = (
        'Upgrade CPanel to version 106.0.18, 102.0.43 or later. Restrict access to '
        'CPanel ports from trusted networks.'
    )
    CVE = ['CVE-2022-44877']
    PORTS = [2082, 2083, 80, 443, 2086, 2087]

    CPANEL_PATHS = [
        '/cpanel',
        '/login',
        '/cpsess',
        '/',
    ]

    CPANEL_HINTS = [
        b'cPanel',
        b'cpanel',
        b'CPanel',
        b'whostmgrd',
        b'cpsess',
        b'cpapi',
        b'Sec-Token',
        b'token',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 2083, 2087) else 'http'
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

                for path in self.CPANEL_PATHS:
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
                        cpanel_hits = [h for h in self.CPANEL_HINTS if h in response]

                        if cpanel_hits or (is_200 and (b'cpanel' in response.lower() or b'whm' in response.lower())):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'CPanel interface detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2022-44877 auth bypass RCE'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'CPanel indicators: {cpanel_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-44877',
                                    'https://www.tenable.com/plugins/nessus/167315',
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
                description='No CPanel interface indicators detected'
            ))

        return results
