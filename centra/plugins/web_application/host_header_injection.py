"""
Plugin 1136: Host Header Injection Detection
==============================================
Detects Host header injection vulnerabilities by sending requests with modified Host headers.
Real CVEs: CVE-2024-22252 (VMware), CVE-2023-38545 (cache poisoning)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class HostHeaderInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1136
    NAME = 'Host Header Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects Host header injection vulnerabilities by sending requests with '
        'modified Host headers. If the server reflects the Host header value in '
        'redirects, links, or responses, an attacker can poison caches, reset '
        'passwords, or bypass security controls.'
    )
    SOLUTION = (
        'Use absolute URLs in redirects. Validate Host header against a whitelist. '
        'Do not forward Host header to backend without validation.'
    )
    CVE = ['CVE-2024-22252', 'CVE-2023-38545']
    PORTS = [80, 443, 8080, 8443]

    MALICIOUS_HOST = 'attacker.com'
    PROBE_VALUE = 'centra_host_injection'

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
                host_header = self.MALICIOUS_HOST
                req = (
                    f'GET / HTTP/1.1\r\n'
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

                body = response.decode('utf-8', errors='ignore')
                if self.MALICIOUS_HOST in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description='Host header injection vulnerability detected. Server reflects malicious Host header in response.',
                        solution=self.SOLUTION,
                        evidence=f'Host header "{self.MALICIOUS_HOST}" reflected in response body',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2024-22252',
                            'https://portswigger.net/web-security/host-header-attacks',
                        ]
                    ))
                    return results

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
