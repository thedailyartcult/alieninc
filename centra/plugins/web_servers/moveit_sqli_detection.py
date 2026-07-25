"""
Plugin 1096: Progress MOVEit Transfer SQL Injection (CVE-2023-34362)
====================================================================
Detects SQL injection vulnerability in Progress MOVEit Transfer.
Real CVE: CVE-2023-34362 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class MoveitSqliDetection(NaslPlugin):
    PLUGIN_ID = 1096
    NAME = 'Progress MOVEit Transfer SQL Injection (CVE-2023-34362)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Progress MOVEit Transfer before 2021.0.6 (13.0.6), 2021.1.4 (13.1.4), '
        '2022.0.4 (14.0.4), 2022.1.5 (14.1.5), and 2023.0.1 (15.0.1) contains '
        'a SQL injection vulnerability in the web application. An unauthenticated '
        'attacker can access the MOVEit database, read sensitive data, and '
        'potentially execute arbitrary SQL commands. Mass-exploited by Cl0p '
        'ransomware gang affecting 2,700+ organizations.'
    )
    SOLUTION = (
        'Upgrade MOVEit Transfer to patched version per vendor advisory. '
        'Block external access to MOVEit web interface if possible.'
    )
    CVE = ['CVE-2023-34362']
    PORTS = [80, 443, 8080, 8443]

    MOVEIT_PATHS = ['/moveit/moveitlogin.jsp']
    MOVEIT_INDICATORS = [
        b'MOVEit',
        b'MOVEitLogin',
        b'moveitlogin',
        b'/moveit/',
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

                for path in self.MOVEIT_PATHS:
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
                        moveit_detected = any(indicator in response for indicator in self.MOVEIT_INDICATORS)

                        if moveit_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'MOVEit Transfer detected on port {port_to_check} — '
                                    f'potentially vulnerable to SQL injection (CVE-2023-34362)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'MOVEit indicators found: {moveit_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-34362',
                                    'https://www.tenable.com/plugins/nessus/176417',
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
                description='No MOVEit Transfer indicators detected on checked ports'
            ))

        return results
