"""
Plugin 1080: PaperCut MF/NG Auth Bypass RCE (CVE-2023-27350)
==============================================================
Detects PaperCut authentication bypass leading to RCE.
Real CVE: CVE-2023-27350 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class PapercutRceDetection(NaslPlugin):
    PLUGIN_ID = 1080
    NAME = 'PaperCut MF/NG Authentication Bypass RCE (CVE-2023-27350)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'PaperCut NG and MF versions 8.0.0 through 22.0.8 contain an improper access '
        'control vulnerability in the SetupCompleted Java class. An unauthenticated '
        'attacker can bypass authentication and access the admin interface. Once '
        'authenticated, the attacker can use the scripting interface to execute '
        'arbitrary code as SYSTEM. Actively exploited by Bl00dy ransomware gang.'
    )
    SOLUTION = (
        'Upgrade PaperCut to version 22.0.9 or later. Block external access to '
        'PaperCut web interface. Monitor for unauthorized access to SetupCompleted page.'
    )
    CVE = ['CVE-2023-27350']
    PORTS = [9191, 9192, 80, 443, 8080]

    PAPERCUT_PATHS = [
        '/app?service=page/SetupCompleted',
        '/setupCompleted',
        '/app',
    ]

    PAPERCUT_HINTS = [
        b'PaperCut',
        b'papercut',
        b'SetupCompleted',
        b'Approve Release',
        b'print release',
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

                for path in self.PAPERCUT_PATHS:
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
                        papercut_hits = [h for h in self.PAPERCUT_HINTS if h.lower() in response.lower()]

                        if is_200 and papercut_hits:
                            setup_completed = b'SetupCompleted' in response or b'setupCompleted' in response
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'PaperCut web interface detected on port {port_to_check} — '
                                    f'SetupCompleted endpoint may be accessible (CVE-2023-27350)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'SetupCompleted accessible: {setup_completed}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-27350',
                                    'https://www.horizon3.ai/papercut-cve-2023-27350-deep-dive/',
                                    'https://www.tenable.com/plugins/nessus/174246',
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
                description='No PaperCut indicators detected on checked ports'
            ))

        return results
