"""
Plugin 1082: Confluence OGNL RCE (CVE-2022-26134)
===================================================
Detects unauthenticated OGNL injection in Atlassian Confluence.
Real CVE: CVE-2022-26134 (CVSS 9.8)
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class ConfluenceOgnlDetection(NaslPlugin):
    PLUGIN_ID = 1082
    NAME = 'Atlassian Confluence OGNL Injection RCE (CVE-2022-26134)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Atlassian Confluence Server and Data Center versions before 7.4.17, 7.13.7, '
        '7.14.3, 7.15.2, 7.16.4, 7.17.4, and 7.18.1 are vulnerable to unauthenticated '
        'OGNL injection. An attacker can send a specially crafted HTTP request to '
        'execute arbitrary code on the Confluence server. This vulnerability was '
        'actively exploited within hours of public disclosure.'
    )
    SOLUTION = (
        'Upgrade Confluence to the latest patched version. As an emergency mitigation, '
        'block external access to Confluence. Apply WAF rules to block OGNL injection patterns.'
    )
    CVE = ['CVE-2022-26134']
    PORTS = [8090, 8080, 443, 80]

    CONFLUENCE_PATHS = ['/', '/login', '/dashboard']

    OGNL_PROBES = [
        ('${42+42}', b'84'),
        ('${8*7}', b'56'),
        ('${108-66}', b'42'),
    ]

    CONFLUENCE_HINTS = [
        b'Confluence',
        b'Atlassian',
        b'AJS',
        b'confluence',
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

                found = False
                for path in self.CONFLUENCE_PATHS:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'

                    for ognl_expr, expected_value in self.OGNL_PROBES:
                        encoded = urllib.parse.quote(ognl_expr)
                        get_path = f'{path}?test={encoded}'

                        req = (
                            f'GET {get_path} HTTP/1.1\r\n'
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

                        if not response:
                            continue

                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')

                        ognl_evaluated = expected_value in body
                        confluence_detected = any(h in response for h in self.CONFLUENCE_HINTS)

                        if ognl_evaluated:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Confluence OGNL injection confirmed on port {port_to_check} '
                                    f'— expression {ognl_expr} was evaluated in response'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'OGNL: {ognl_expr} => {expected_value.decode()} found in body'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-26134',
                                    'https://www.tenable.com/plugins/nessus/161509',
                                ]
                            ))
                            found = True
                            break

                    writer.close()
                    await writer.wait_closed()
                    if found:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Confluence OGNL injection indicators detected on checked ports'
            ))

        return results
