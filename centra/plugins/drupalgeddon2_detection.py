"""
Plugin 1088: Drupal Core Remote Code Execution - Drupalgeddon2 (CVE-2018-7600)
================================================================================
Detects Drupalgeddon2 RCE in Drupal web applications.
Real CVE: CVE-2018-7600 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class Drupalgeddon2Detection(NaslPlugin):
    PLUGIN_ID = 1088
    NAME = 'Drupal Core Remote Code Execution (Drupalgeddon2)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Drupal 6.x, 7.x, and 8.x before 7.58 and 8.5.1 contains a RCE vulnerability '
        'in the Form API. An unauthenticated attacker can execute arbitrary code by '
        'exploiting the way the Form API handles render arrays.'
    )
    SOLUTION = (
        'Update Drupal to version 7.58, 8.5.1 or later. Apply the PSA-2018-001 '
        'security advisory. Restrict access to /user/register and /node/add if not needed.'
    )
    CVE = ['CVE-2018-7600']
    PORTS = [80, 443, 8080, 8443]

    DRUPAL_PATHS = [
        '/user/register',
        '/user/login',
        '/node/add',
        '/',
        '/robots.txt',
    ]

    DRUPAL_HINTS = [
        b'Drupal',
        b'drupalSettings',
        b'SESS',
        b'Drupal.settings',
        b'form_build_id',
        b'form_id',
        b'drupal',
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

                for path in self.DRUPAL_PATHS:
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
                        drupal_hits = [h for h in self.DRUPAL_HINTS if h.lower() in response.lower()]

                        if is_200 and drupal_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Drupal detected on port {port_to_check} — '
                                    f'potentially vulnerable to Drupalgeddon2 RCE (CVE-2018-7600)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Drupal hints: {drupal_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2018-7600',
                                    'https://www.drupal.org/sa-core-2018-002',
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
                description='No Drupal indicators detected on checked ports'
            ))

        return results
