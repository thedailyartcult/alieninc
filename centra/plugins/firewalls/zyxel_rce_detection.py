"""
Plugin 1112: Zyxel Firewall RCE (CVE-2023-28771)
=================================================
Detects CVE-2023-28771 RCE in Zyxel firewalls.
Real CVE: CVE-2023-28771 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ZyxelRceDetection(NaslPlugin):
    PLUGIN_ID = 1112
    NAME = 'Zyxel Firewall RCE (CVE-2023-28771)'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Zyxel ATP, USG, USG FLEX, and VPN series firewalls with firmware 4.32 through '
        '5.35 contain an unauthenticated remote code execution vulnerability. Improper '
        'error message parsing in the IKE packet handler allows command injection.'
    )
    SOLUTION = (
        'Upgrade Zyxel firewall firmware to patched version. Restrict VPN access from '
        'untrusted networks.'
    )
    CVE = ['CVE-2023-28771']
    PORTS = [443, 80, 8443, 8080]

    ZYXEL_PATHS = [
        '/',
        '/login',
        '/cgi-bin/',
        '/cgi-bin/login',
        '/api/',
    ]

    ZYXEL_HINTS = [
        b'Zyxel',
        b'zyxel',
        b'ZYXEL',
        b'USG',
        b'ATP',
        b'VPN',
        b'ZyWALL',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
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

                for path in self.ZYXEL_PATHS:
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
                        zyxel_hits = [h for h in self.ZYXEL_HINTS if h in response]

                        if zyxel_hits or (is_200 and b'zyxel' in response.lower()):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Zyxel firewall detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2023-28771 RCE'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Zyxel indicators: {zyxel_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-28771',
                                    'https://www.zyxel.com/support/security_advisories.shtml',
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
                description='No Zyxel firewall indicators detected'
            ))

        return results
