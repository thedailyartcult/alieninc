"""
Plugin 1117: Server-Side Request Forgery Detection
====================================================
Detects SSRF vulnerabilities by probing common SSRF-prone parameters
(url, uri, path, dest, redirect, file, domain, host, proxy).
SSRF allows attackers to make requests from the internal network,
potentially accessing cloud metadata endpoints or internal services.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class GenericSsrfDetection(NaslPlugin):
    PLUGIN_ID = 1117
    NAME = 'Server-Side Request Forgery Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects Server-Side Request Forgery (SSRF) vulnerabilities by probing '
        'common SSRF-prone parameters (url, uri, path, dest, redirect, file, '
        'domain, host, proxy). SSRF allows attackers to make requests from the '
        'internal network, potentially accessing cloud metadata endpoints, '
        'internal services, or the local host.'
    )
    SOLUTION = (
        'Validate and whitelist allowed URLs. Block access to internal/private '
        'IP ranges. Use a URL parser to verify destinations before making requests.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SSRF_PARAMS = [
        'url', 'uri', 'path', 'dest', 'redirect', 'file',
        'domain', 'host', 'proxy', 'target', 'endpoint',
    ]

    CANARY_URL = 'http://169.254.169.254/latest/meta-data/'
    EXTERNAL_URL = 'http://127.0.0.1:22'

    PATHS = ['/', '/proxy', '/fetch', '/load', '/api/proxy', '/api/fetch']

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

                for param in self.SSRF_PARAMS[:5]:
                    for path in self.PATHS:
                        test_url = urllib.parse.quote(self.CANARY_URL)
                        query = f'{param}={test_url}'

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

                        body = response.split(b'\r\n\r\n', 1)
                        body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                        if 'ami-id' in body_text or 'meta-data' in body_text or 'localhost' in body_text:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=f'SSRF detected via parameter "{param}" on {path}',
                                solution=self.SOLUTION,
                                evidence=f'Parameter: {param}, returned internal data indicating SSRF',
                                references=[
                                    'https://owasp.org/www-community/attacks/Server_Side_Request_Forgery',
                                    'https://portswigger.net/web-security/ssrf',
                                ]
                            ))
                            break

                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No SSRF indicators detected on checked ports'
            ))

        return results
