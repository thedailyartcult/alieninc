"""
Plugin 1139: HTTP Parameter Pollution Detection
=================================================
Detects HTTP Parameter Pollution (HPP) by sending multiple parameters with the same name.
Real CVEs: CVE-2023-37938 (parameter pollution), CVE-2022-39227
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ParameterPollutionDetection(NaslPlugin):
    PLUGIN_ID = 1139
    NAME = 'HTTP Parameter Pollution Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects HTTP Parameter Pollution (HPP) by sending multiple parameters '
        'with the same name and observing which value the server prefers. Parameter '
        'pollution can bypass security filters, override application logic, or cause '
        'unexpected behavior.'
    )
    SOLUTION = (
        'Use deterministic parameter parsing. Reject requests with duplicate '
        'parameters. Use strict parameter whitelisting.'
    )
    CVE = ['CVE-2023-37938', 'CVE-2022-39227']
    PORTS = [80, 443, 8080, 8443]

    PROBE_VALUE = 'centra_hpp_test'

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
                    f'GET /?id=1&id=2&id=3 HTTP/1.1\r\n'
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
                if 'id=1' in response_text or 'id=2' in response_text or 'id=3' in response_text:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description='HTTP Parameter Pollution detected. Server reflects or processes duplicate parameters.',
                        solution=self.SOLUTION,
                        evidence='Request with ?id=1&id=2&id=3 resulted in parameter values appearing in response',
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2023-37938',
                            'https://owasp.org/www-community/attacks/Parameter_Pollution',
                        ]
                    ))
                    return results

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
