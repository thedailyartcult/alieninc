"""
Plugin 1074: Fortra GoAnywhere MFT Auth Bypass (CVE-2024-0204)
================================================================
Detects authentication bypass in Fortra GoAnywhere MFT that allows
unauthorized users to create admin accounts via the administration portal.
Real CVEs: CVE-2024-0204 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GoanywhereAuthBypass(NaslPlugin):
    PLUGIN_ID = 1074
    NAME = 'Fortra GoAnywhere MFT Auth Bypass (CVE-2024-0204)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Authentication bypass in Fortra GoAnywhere MFT prior to 7.4.1 allows '
        'an unauthorized user to create an admin user via the administration '
        'portal. An unauthenticated attacker can trigger a path traversal '
        'against the InitialAccountSetup.xhtml endpoint, bypass security '
        'filters, and create a new administrator account. This can lead to '
        'complete system compromise, data exfiltration, and ransomware deployment.'
    )
    SOLUTION = (
        'Upgrade GoAnywhere MFT to version 7.4.1 or later immediately. '
        'If upgrade is not possible, restrict network access to the '
        'administration portal. Monitor for unauthorized account creation. '
        'Review access logs for suspicious activity targeting '
        'InitialAccountSetup.xhtml.'
    )
    CVE = ['CVE-2024-0204']
    PORTS = [8000, 8001, 8080, 8443, 443]

    VULNERABLE_ENDPOINTS = [
        '/InitialAccountSetup.xhtml',
        '/goanywhere/InitialAccountSetup.xhtml',
        '/MFT/InitialAccountSetup.xhtml',
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

                for endpoint in self.VULNERABLE_ENDPOINTS:
                    req = (
                        f'GET {endpoint} HTTP/1.1\r\n'
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

                        if b'200 OK' in response and (
                            b'InitialAccountSetup' in response
                            or b'Create Admin' in body
                            or b'GoAnywhere' in body
                        ):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=f'GoAnywhere MFT InitialAccountSetup endpoint exposed on port {port_to_check}',
                                solution=self.SOLUTION,
                                evidence=f'Endpoint: {endpoint}, Status: {status_line}',
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2024-0204',
                                    'https://www.horizon3.ai/cve-2024-0204-goanywhere-mft-auth-bypass-deep-dive/',
                                    'https://github.com/horizon3ai/CVE-2024-0204',
                                ]
                            ))

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='GoAnywhere MFT administration portal not detected or not vulnerable'
            ))

        return results
