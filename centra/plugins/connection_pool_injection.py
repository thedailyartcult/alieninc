"""
Plugin 1242: HTTP Connection Pool Injection Detection
=====================================================
Detects HTTP connection pool injection vulnerabilities where attackers can
cause HTTP requests to be sent to different backends.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ConnectionPoolInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1242
    NAME = 'HTTP Connection Pool Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects HTTP connection pool injection vulnerabilities where attackers '
        'can cause HTTP requests to be sent to different backends by manipulating '
        'the Host header or connection reuse patterns in HTTP/1.1 persistent '
        'connections.'
    )
    SOLUTION = (
        'Use HTTP/2 which eliminates connection reuse ambiguity. Validate backend '
        'routing decisions. Use strict Host header validation.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    MALICIOUS_HOSTS = [
        'evil.com',
        '127.0.0.1',
        'localhost',
        '0.0.0.0',
        'internal.service',
        'metadata.google.internal',
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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                legit_responses = []
                for malicious_host in self.MALICIOUS_HOSTS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        req1 = (
                            f'GET / HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: keep-alive\r\n\r\n'
                        )
                        writer.write(req1.encode())
                        await writer.drain()
                        resp1 = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk:
                                    break
                                resp1 += chunk
                                if resp1.count(b'\r\n\r\n') > 1 or len(resp1) > 2048:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        req2 = (
                            f'GET / HTTP/1.1\r\n'
                            f'Host: {malicious_host}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                        )
                        writer.write(req2.encode())
                        await writer.drain()
                        resp2 = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk:
                                    break
                                resp2 += chunk
                                if len(resp2) > 2048:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()
                        if resp1 and resp2:
                            status1 = resp1.split(b'\r\n')[0] if resp1 else b''
                            status2 = resp2.split(b'\r\n')[0] if resp2 else b''
                            if status1 != status2 and resp1 != resp2:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='medium',
                                    description=(
                                        f'Connection pool injection possible - different responses '
                                        f'for Host header "{malicious_host}" vs legitimate host on '
                                        f'same connection'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Legit host: {host_header} -> {status1.decode()}, malicious host: {malicious_host} -> {status2.decode()}',
                                    references=[
                                        'https://portswigger.net/research/http-connection-pool-injection',
                                        'https://www.acunetix.com/vulnerabilities/web/http-connection-pool-injection/',
                                    ]
                                ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                    if results:
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No connection pool injection indicators detected'
            ))
        return results
