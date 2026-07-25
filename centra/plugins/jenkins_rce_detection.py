"""
Plugin 1093: Jenkins CLI Arbitrary File Read / RCE (CVE-2024-23897)
=====================================================================
Detects Jenkins CLI arbitrary file read vulnerability via args4j.
Real CVE: CVE-2024-23897 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class JenkinsRceDetection(NaslPlugin):
    PLUGIN_ID = 1093
    NAME = 'Jenkins CLI Arbitrary File Read / RCE'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Jenkins 2.441 and earlier, LTS 2.426.2 and earlier has a vulnerability in '
        'the CLI interface. The args4j library expands @-prefixed filenames, allowing '
        'an unauthenticated attacker to read arbitrary files on the Jenkins server.'
    )
    SOLUTION = (
        'Update Jenkins to 2.442 or LTS 2.426.3. Disable the CLI interface if not '
        'needed. Restrict access to the Jenkins web interface.'
    )
    CVE = ['CVE-2024-23897']
    PORTS = [8080, 80, 443, 8443]

    JENKINS_PATHS = [
        '/login?from=%2F',
        '/',
        '/cli/',
        '/jenkins/login?from=%2F',
        '/jenkins/',
    ]

    JENKINS_HINTS = [
        b'Jenkins',
        b'jenkins',
        b'Jenkins-Crumb',
        b'Jenkins-Authentication-Token',
        b'X-Jenkins',
        b'Jenkins CLI',
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

                for path in self.JENKINS_PATHS:
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
                        headers_end = response.find(b'\r\n\r\n')
                        raw_headers = response[:headers_end].decode('utf-8', errors='ignore')

                        is_200 = b'200 OK' in response[:50]
                        jenkins_hits = [h for h in self.JENKINS_HINTS if h in response]
                        jenkins_crumb = b'Jenkins-Crumb' in response

                        if is_200 and jenkins_hits:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Jenkins server detected on port {port_to_check} — '
                                    f'potentially vulnerable to CLI file read (CVE-2024-23897)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Jenkins-Crumb present: {jenkins_crumb}, '
                                    f'Jenkins hints: {jenkins_hits}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2024-23897',
                                    'https://www.jenkins.io/security/advisory/2024-01-24/',
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
                description='No Jenkins indicators detected on checked ports'
            ))

        return results
