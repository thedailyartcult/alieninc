"""
Plugin 1099: F5 BIG-IP iControl REST RCE (CVE-2022-1388)
==========================================================
Detects unauthenticated RCE in F5 BIG-IP iControl REST API.
Real CVE: CVE-2022-1388 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class F5BigipRceDetection(NaslPlugin):
    PLUGIN_ID = 1099
    NAME = 'F5 BIG-IP iControl REST RCE (CVE-2022-1388)'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'F5 BIG-IP 11.6.x, 12.1.x, 13.1.x, 14.1.x, 15.1.x, 16.0.x, and 16.1.x '
        'before patched versions allows unauthenticated RCE via the iControl REST '
        'API. An attacker can bypass authentication by sending a crafted request '
        'with a manipulated Connection header and X-F5-Auth-Token header.'
    )
    SOLUTION = (
        'Apply F5 security update K23605346. '
        'Block external access to iControl REST API (/mgmt/tm).'
    )
    CVE = ['CVE-2022-1388']
    PORTS = [443, 8443, 80, 8080, 10443]

    ICONTROL_PATHS = ['/mgmt/tm/util/bash']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 10443) else 'http'
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

                for path in self.ICONTROL_PATHS:
                    body = '{"command":"run","utilCmdArgs":"-c id"}'
                    req = (
                        f'POST {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Content-Type: application/json\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n'
                        f'{body}'
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

                        f5_indicators = [
                            'iControl',
                            '/mgmt/tm',
                            'F5',
                            'BIG-IP',
                            'kind',
                            'selfLink',
                            'commandResult',
                            'generation',
                        ]
                        found_f5 = [h for h in f5_indicators if h.lower() in body_str.lower()]
                        is_200 = b'200 OK' in response[:50]

                        if found_f5 or is_200:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'F5 BIG-IP iControl REST API detected on port '
                                    f'{port_to_check} — potentially vulnerable to '
                                    f'unauthenticated RCE (CVE-2022-1388)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'F5 indicators: {found_f5}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-1388',
                                    'https://www.tenable.com/plugins/nessus/160084',
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
                description='No F5 BIG-IP iControl REST API indicators detected on checked ports'
            ))

        return results
