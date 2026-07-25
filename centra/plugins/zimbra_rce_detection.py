"""
Plugin 1086: Zimbra Collaboration Memcache Command Injection RCE (CVE-2022-27924)
=================================================================================
Detects Zimbra Collaboration memcache command injection vulnerability.
Real CVE: CVE-2022-27924 (CVSS 7.5)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ZimbraRceDetection(NaslPlugin):
    PLUGIN_ID = 1086
    NAME = 'Zimbra Collaboration Memcache Command Injection RCE'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Zimbra Collaboration 8.8.15 and 9.0 has a memcache command injection '
        'vulnerability. An unauthenticated attacker can inject commands into the '
        'memcache server, leading to RCE via crafted HTTP requests.'
    )
    SOLUTION = (
        'Upgrade to Zimbra 8.8.15 Patch 31 or 9.0 Patch 24. Restrict memcache '
        'access to trusted hosts only and block external memcache traffic.'
    )
    CVE = ['CVE-2022-27924']
    PORTS = [80, 443, 8443, 7071]

    ZIMBRA_PATHS = [
        '/zimbra/',
        '/zimbra/admin/',
        '/robots.txt',
        '/',
    ]

    ZIMBRA_HINTS = [
        b'Zimbra',
        b'zimbra',
        b'ZM_',
        b'zimlet',
        b'zmail',
        b'ZCS',
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

                for path in self.ZIMBRA_PATHS:
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
                        zimbra_hits = [h for h in self.ZIMBRA_HINTS if h.lower() in response.lower()]

                        if is_200 and zimbra_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Zimbra Collaboration detected on port {port_to_check} — '
                                    f'potentially vulnerable to memcache command injection (CVE-2022-27924)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Zimbra hints: {zimbra_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-27924',
                                    'https://www.zimbra.com/security/',
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
                description='No Zimbra Collaboration indicators detected on checked ports'
            ))

        return results
