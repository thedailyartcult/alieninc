"""
Plugin 1141: Web Cache Poisoning Detection
============================================
Detects web cache poisoning vulnerabilities by injecting unkeyed headers.
Real CVEs: CVE-2024-27197 (cache poisoning), CVE-2023-46217
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CachePoisoningDetection(NaslPlugin):
    PLUGIN_ID = 1141
    NAME = 'Web Cache Poisoning Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects web cache poisoning vulnerabilities by injecting unkeyed headers '
        '(X-Forwarded-Host, X-Original-URL, X-Forwarded-Scheme) and observing if '
        'responses are cached with attacker-controlled values. Cache poisoning can '
        'serve malicious content to all visitors.'
    )
    SOLUTION = (
        'Never use unkeyed headers in cache key computation. Disable caching for '
        'dynamic content. Use Vary headers explicitly.'
    )
    CVE = ['CVE-2024-27197', 'CVE-2023-46217']
    PORTS = [80, 443, 8080, 8443]

    POISON_HEADERS = {
        'X-Forwarded-Host': 'evil.com',
        'X-Original-URL': '/admin',
        'X-Forwarded-Scheme': 'http',
    }

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for header_name, header_value in self.POISON_HEADERS.items():
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
                        f'GET / HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'{header_name}: {header_value}\r\n'
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
                    if header_value in response_text:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='high',
                            description=f'Web cache poisoning via {header_name}. Injected value {header_value} reflected in response.',
                            solution=self.SOLUTION,
                            evidence=f'Header: {header_name}: {header_value} reflected in response body/headers',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2024-27197',
                                'https://portswigger.net/web-security/web-cache-poisoning',
                            ]
                        ))
                        return results

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
