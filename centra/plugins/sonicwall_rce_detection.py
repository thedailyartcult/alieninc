"""
Plugin 1095: SonicWall SMA 100 Series SSL VPN SQL Injection RCE (CVE-2021-20016)
==================================================================================
Detects SonicWall SMA SQL injection vulnerability leading to RCE.
Real CVE: CVE-2021-20016 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class SonicwallRceDetection(NaslPlugin):
    PLUGIN_ID = 1095
    NAME = 'SonicWall SMA 100 Series SSL VPN SQL Injection RCE'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'SonicWall SMA 100 Series SSL VPN appliances (SMA 200, 210, 400, 410) before '
        '10.2.0.9-34sv and SMA 500v before 10.2.0.9-34sv contain a SQL injection '
        'vulnerability in the web management interface. An unauthenticated attacker '
        'can execute arbitrary SQL commands potentially leading to RCE.'
    )
    SOLUTION = (
        'Upgrade SonicWall SMA firmware to 10.2.0.9-34sv or later. Restrict '
        'management access to trusted IPs only. Disable WAN management if not needed.'
    )
    CVE = ['CVE-2021-20016']
    PORTS = [443, 8443, 80]

    SONICWALL_PATHS = [
        '/cgi-bin/portal',
        '/cgi-bin/login',
        '/cgi-bin/jarrewrite.cgi',
        '/',
    ]

    SONICWALL_HINTS = [
        b'SonicWALL',
        b'SonicWall',
        b'sonicwall',
        b'SMA',
        b'SSLVPN',
        b'/cgi-bin/portal',
        b'defportal',
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

                for path in self.SONICWALL_PATHS:
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

                        is_200 = b'200 OK' in response[:50]
                        sonicwall_hits = [h for h in self.SONICWALL_HINTS if h in response]

                        if sonicwall_hits or (is_200 and b'portal' in response.lower() and b'cgi' in response.lower()):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'SonicWall SMA SSL VPN detected on port {port_to_check} — '
                                    f'potentially vulnerable to SQL injection (CVE-2021-20016)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'SonicWall hints: {sonicwall_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-20016',
                                    'https://psirt.global.sonicwall.com/vuln-detail/SNWLID-2021-0003',
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
                description='No SonicWall SMA SSL VPN indicators detected'
            ))

        return results
