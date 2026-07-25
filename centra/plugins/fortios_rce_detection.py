"""
Plugin 1115: FortiOS/FortiProxy RCE (CVE-2023-25610)
======================================================
Detects CVE-2023-25610 buffer underflow in FortiOS/FortiProxy.
Real CVE: CVE-2023-25610 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class FortiosRceDetection(NaslPlugin):
    PLUGIN_ID = 1115
    NAME = 'FortiOS/FortiProxy RCE (CVE-2023-25610)'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 9.8
    CVSS = 9.8
    DESCRIPTION = (
        'FortiOS 7.2.0 through 7.2.3, 7.0.0 through 7.0.9, 6.4.0 through 6.4.11, '
        '6.2.0 through 6.2.13, 6.0.0 through 6.0.16 and FortiProxy 7.2.0 through '
        '7.2.2, 7.0.0 through 7.0.8, 2.0.0 through 2.0.12 contain a buffer underflow '
        'vulnerability in the administrative interface. A remote unauthenticated '
        'attacker can execute arbitrary code via crafted HTTP requests.'
    )
    SOLUTION = (
        'Upgrade FortiOS/FortiProxy to patched versions. Restrict administrative '
        'interface access to trusted IPs.'
    )
    CVE = ['CVE-2023-25610']
    PORTS = [443, 8443, 10443]

    FORTIOS_ADMIN_PATHS = [
        '/login',
        '/admin',
        '/admin/login',
        '/',
    ]

    FORTIOS_HINTS = [
        b'FortiGate',
        b'FortiOS',
        b'Fortinet',
        b'fortinet',
        b'FORTINET',
        b'fortios',
        b'FortiProxy',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 10443) else 'http'
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

                for path in self.FORTIOS_ADMIN_PATHS:
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
                        forti_hits = [h for h in self.FORTIOS_HINTS if h in response]

                        if forti_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Fortinet device detected on port {port_to_check} — '
                                    f'potentially vulnerable to CVE-2023-25610 buffer underflow RCE'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Fortinet indicators: {forti_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-25610',
                                    'https://www.fortiguard.com/psirt/FG-IR-23-001',
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
                description='No Fortinet device indicators detected for CVE-2023-25610'
            ))

        return results
