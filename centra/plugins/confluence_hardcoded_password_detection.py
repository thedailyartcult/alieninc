"""
Plugin 1105: Confluence Questions Hardcoded Password (CVE-2022-26138)
=====================================================================
Detects hardcoded password vulnerability in Atlassian Questions for Confluence.
Real CVE: CVE-2022-26138 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ConfluenceHardcodedPasswordDetection(NaslPlugin):
    PLUGIN_ID = 1105
    NAME = 'Confluence Questions Hardcoded Password (CVE-2022-26138)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'The Atlassian Questions for Confluence app (versions 2.7.x, 3.0.x) '
        'contains a hardcoded password vulnerability. A local system account '
        'with username disabledsystemuser and password disabled1SystemUser is '
        'created when the app is installed. An attacker can use these credentials '
        'to access Confluence with elevated privileges.'
    )
    SOLUTION = (
        'Upgrade Questions for Confluence to 2.7.38, 3.0.12 or later. '
        'Remove or disable the disabledsystemuser account immediately.'
    )
    CVE = ['CVE-2022-26138']
    PORTS = [80, 443, 8080, 8443, 8090]

    QUESTIONS_PATHS = ['/questions/', '/confluence/', '/confluence/questions/']
    QUESTIONS_INDICATORS = [
        b'Questions',
        b'questions',
        b'disabledsystemuser',
        b'Confluence Questions',
        b'atlassian-questions',
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

                for path in self.QUESTIONS_PATHS:
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
                        questions_detected = any(indicator in response for indicator in self.QUESTIONS_INDICATORS)

                        if questions_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Confluence Questions app detected on port '
                                    f'{port_to_check} — may have hardcoded password '
                                    f'vulnerability (CVE-2022-26138)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Questions app indicators found: {questions_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-26138',
                                    'https://www.tenable.com/plugins/nessus/162596',
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
                description='No Confluence Questions hardcoded password indicators detected on checked ports'
            ))

        return results
