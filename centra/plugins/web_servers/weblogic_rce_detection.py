"""
Plugin 1089: Oracle WebLogic Server Administration Console RCE (CVE-2020-14882)
================================================================================
Detects Oracle WebLogic Server unauthenticated RCE via admin console.
Real CVE: CVE-2020-14882 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class WeblogicRceDetection(NaslPlugin):
    PLUGIN_ID = 1089
    NAME = 'Oracle WebLogic Server Administration Console RCE'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Oracle WebLogic Server 10.3.6.0.0, 12.1.3.0.0, 12.2.1.3.0, 12.2.1.4.0, '
        'and 14.1.1.0.0 allows unauthenticated RCE through the administration console. '
        'An attacker can bypass authentication and execute arbitrary commands.'
    )
    SOLUTION = (
        'Apply the Oracle Critical Patch Update October 2020. Restrict access to '
        'the admin console paths (/console/, /bea_wls_internal/). Use a WAF to '
        'block unauthenticated access to the admin console.'
    )
    CVE = ['CVE-2020-14882']
    PORTS = [7001, 7002, 80, 443]

    WEBLOGIC_PATHS = [
        '/console/login/LoginForm.jsp',
        '/console/',
        '/bea_wls_internal/',
        '/wls-wsat/',
    ]

    WEBLOGIC_HINTS = [
        b'WebLogic',
        b'weblogic',
        b'WebLogic Server',
        b'LoginForm',
        b'Oracle WebLogic',
        b'WebLogicServer',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 7002) else 'http'
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

                for path in self.WEBLOGIC_PATHS:
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
                        weblogic_hits = [h for h in self.WEBLOGIC_HINTS if h in response]

                        if weblogic_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Oracle WebLogic Server detected on port {port_to_check} — '
                                    f'admin console may be vulnerable to unauthenticated RCE (CVE-2020-14882)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'WebLogic hints: {weblogic_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2020-14882',
                                    'https://www.oracle.com/security-alerts/cpuoct2020.html',
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
                description='No Oracle WebLogic Server indicators detected on checked ports'
            ))

        return results
