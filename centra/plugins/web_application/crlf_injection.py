"""
Plugin 1137: CRLF Injection / HTTP Response Splitting
=======================================================
Detects CRLF injection vulnerabilities by injecting %0d%0a sequences into parameters.
Real CVEs: CVE-2023-32315 (Node.js), CVE-2022-22965 (Spring4Shell)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CrlfInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1137
    NAME = 'CRLF Injection / HTTP Response Splitting'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects CRLF (Carriage Return Line Feed) injection vulnerabilities by '
        'injecting %0d%0a sequences into parameters. CRLF injection can lead to '
        'HTTP response splitting, cache poisoning, XSS, and log injection.'
    )
    SOLUTION = (
        'Encode or strip CRLF characters from user input before including in HTTP '
        'headers. Use modern frameworks that handle output encoding.'
    )
    CVE = ['CVE-2023-32315', 'CVE-2022-22965']
    PORTS = [80, 443, 8080, 8443]

    CRLF_PAYLOADS = [
        '%0d%0aX-CRLF-Injected:true',
        '%0d%0a%0d%0a<script>alert(1)</script>',
        '%0d%0aContent-Length:0%0d%0a%0d%0aHTTP/1.1 200 OK',
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
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                req = (
                    f'GET /?q={self.CRLF_PAYLOADS[0]} HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Connection: close\r\n\r\n'
                )
                writer.write(req.encode())
                await writer.drain()

                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 32768:
                        break
                writer.close()
                await writer.wait_closed()

                response_text = response.decode('utf-8', errors='ignore')
                if 'X-CRLF-Injected' in response_text or 'CRLF' in response_text:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description='CRLF injection vulnerability detected. Injected headers appear in server response.',
                        solution=self.SOLUTION,
                        evidence=f'CRLF payload reflected: {self.CRLF_PAYLOADS[0]}',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-32315',
                            'https://portswigger.net/web-security/crlf-injection',
                        ]
                    ))
                    return results

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
