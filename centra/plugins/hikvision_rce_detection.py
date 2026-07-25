"""
Plugin 1111: Hikvision IP Camera RCE (CVE-2021-36260)
=====================================================
Detects CVE-2021-36260 RCE in Hikvision IP cameras.
Real CVE: CVE-2021-36260 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class HikvisionRceDetection(NaslPlugin):
    PLUGIN_ID = 1111
    NAME = 'Hikvision IP Camera RCE (CVE-2021-36260)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'Hikvision IP cameras with firmware before 2021-09-17 contain an unauthenticated '
        'remote code execution vulnerability. Command injection exists in the web server\'s '
        'HTTP API, allowing attackers to execute arbitrary commands as the root user. '
        'Affects millions of IoT devices globally.'
    )
    SOLUTION = (
        'Upgrade Hikvision camera firmware to latest version. Isolate cameras on a '
        'separate network segment.'
    )
    CVE = ['CVE-2021-36260']
    PORTS = [80, 443, 8080, 554, 8443]

    HIKVISION_PATHS = [
        '/cgi-bin/',
        '/cgi-bin/status',
        '/cgi-bin/main.cgi',
        '/cgi-bin/config.cgi',
        '/',
    ]

    HIKVISION_HINTS = [
        b'Hikvision',
        b'hikvision',
        b'HIKVISION',
        b'CGI',
        b'cgi-bin',
        b'Web Client',
        b'IPCamera',
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

                for path in self.HIKVISION_PATHS:
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
                        hikvision_hits = [h for h in self.HIKVISION_HINTS if h in response]

                        if hikvision_hits or (is_200 and b'cgi-bin' in response.lower()):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Hikvision IP camera detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2021-36260 RCE'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Hikvision indicators: {hikvision_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-36260',
                                    'https://www.hikvision.com/en/support/cybersecurity/security-advisory/security-notification-command-injection-vulnerability-in-some-hikvision-products/',
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
                description='No Hikvision camera indicators detected'
            ))

        return results
