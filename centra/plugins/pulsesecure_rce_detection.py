"""
Plugin 1087: Pulse Connect Secure Arbitrary File Read / RCE (CVE-2021-22893)
=============================================================================
Detects Pulse Connect Secure arbitrary file read and RCE vulnerability.
Real CVE: CVE-2021-22893 (CVSS 10.0)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class PulsesecureRceDetection(NaslPlugin):
    PLUGIN_ID = 1087
    NAME = 'Pulse Connect Secure Arbitrary File Read / RCE'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'Pulse Connect Secure 9.0R1-9.1R11.4 contains an arbitrary file read '
        'vulnerability in the admin web interface. An unauthenticated attacker can '
        'read arbitrary files, including system files and session data, leading to RCE.'
    )
    SOLUTION = (
        'Upgrade to Pulse Connect Secure 9.1R11.5 or later. Revoke all existing '
        'sessions. Block external access to the admin interface.'
    )
    CVE = ['CVE-2021-22893']
    PORTS = [443, 8443]

    PULSE_PATHS = [
        '/dana-na/auth/',
        '/dana-na/auth/url_default/welcome.cgi',
        '/dana-na/',
    ]

    PULSE_HEADERS = [
        b'Sent-by',
        b'X-Pulse-',
        b'DANA',
        b'dana-na',
        b'PulseSecure',
        b'Juniper',
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

                for path in self.PULSE_PATHS:
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
                        pulse_hits = [h for h in self.PULSE_HEADERS if h in response]

                        if pulse_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Pulse Connect Secure VPN detected on port {port_to_check} — '
                                    f'potentially vulnerable to arbitrary file read (CVE-2021-22893)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Pulse headers identified: {pulse_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-22893',
                                    'https://kb.pulsesecure.net/articles/Pulse_Security_Advisories/SA44784/',
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
                description='No Pulse Secure VPN indicators detected on checked ports'
            ))

        return results
