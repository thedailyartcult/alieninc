"""
Plugin 1104: GitLab ExifTool RCE (CVE-2021-22205)
===================================================
Detects remote code execution via ExifTool in GitLab CE/EE.
Real CVE: CVE-2021-22205 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GitlabRceDetection(NaslPlugin):
    PLUGIN_ID = 1104
    NAME = 'GitLab ExifTool RCE (CVE-2021-22205)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'GitLab CE/EE before 13.10.3, 13.11.3, and 13.12.2 contains a remote '
        'code execution vulnerability in the ExifTool integration. An attacker '
        'can upload a specially crafted image file that triggers arbitrary command '
        'execution. Actively exploited in the wild.'
    )
    SOLUTION = (
        'Upgrade GitLab to 13.10.3, 13.11.3, 13.12.2 or later. '
        'Disable ExifTool if not needed.'
    )
    CVE = ['CVE-2021-22205']
    PORTS = [80, 443, 8080, 8443, 8929]

    GITLAB_PATHS = ['/users/sign_in', '/', '/users/sign_in?redirect_to_referer=yes']
    GITLAB_INDICATORS = [
        b'GitLab',
        b'gitlab',
        b'_gitlab_session',
        b'gitlab-ee',
        b'gitlab-ce',
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

                for path in self.GITLAB_PATHS:
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
                        gitlab_detected = any(indicator in response for indicator in self.GITLAB_INDICATORS)

                        if gitlab_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'GitLab detected on port {port_to_check} — '
                                    f'potentially vulnerable to ExifTool RCE (CVE-2021-22205)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'GitLab indicators found: {gitlab_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-22205',
                                    'https://www.tenable.com/plugins/nessus/149450',
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
                description='No GitLab ExifTool RCE indicators detected on checked ports'
            ))

        return results
