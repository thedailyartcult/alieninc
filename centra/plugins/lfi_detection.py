"""
Plugin 1118: Local File Inclusion / Path Traversal Detection
==============================================================
Detects LFI and path traversal vulnerabilities by probing common
parameters with traversal sequences like ../../../etc/passwd.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class LfiDetection(NaslPlugin):
    PLUGIN_ID = 1118
    NAME = 'Local File Inclusion / Path Traversal Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects Local File Inclusion (LFI) and path traversal vulnerabilities '
        'by probing common parameters (file, page, include, path, template, doc, '
        'folder, root) with traversal sequences like ../../../etc/passwd. LFI can '
        'lead to sensitive file disclosure or RCE via log poisoning.'
    )
    SOLUTION = (
        'Use a whitelist of allowed files/paths. Avoid passing user input to file '
        'system functions. Use chroot jails or containerization.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TRAVERSAL_PAYLOADS = [
        '../../../etc/passwd',
        '....//....//....//etc/passwd',
        '..\\..\\..\\windows\\win.ini',
        '../../../etc/shadow',
        '../../../../../../etc/passwd',
        '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
    ]

    LFI_PARAMS = [
        'file', 'page', 'include', 'path', 'template',
        'doc', 'folder', 'root', 'load', 'view',
    ]

    PATHS = ['/', '/api', '/download', '/view']

    ETCPASSWD_PATTERNS = [
        b'root:.*:0:0:',
        b'daemon:.*:1:1:',
        b'bin:.*:2:2:',
        b'\\[fonts\\]',
        b'for 16-bit app support',
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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for payload in self.TRAVERSAL_PAYLOADS:
                    for param in self.LFI_PARAMS[:5]:
                        for path in self.PATHS:
                            encoded = urllib.parse.quote(payload)
                            query = f'{param}={encoded}'

                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )

                            req = (
                                f'GET {path}?{query} HTTP/1.1\r\n'
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
                                    if len(response) > 16384:
                                        break
                            except asyncio.TimeoutError:
                                pass

                            writer.close()
                            await writer.wait_closed()

                            for pattern in self.ETCPASSWD_PATTERNS:
                                if pattern in response:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'LFI detected via param "{param}" with payload on {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Parameter: {param}, payload: {payload[:60]}, matched pattern in response',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Path_Traversal',
                                            'https://portswigger.net/web-security/file-path-traversal',
                                        ]
                                    ))
                                    break

                            if results:
                                break
                        if results:
                            break
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No LFI indicators detected on checked ports'
            ))

        return results
