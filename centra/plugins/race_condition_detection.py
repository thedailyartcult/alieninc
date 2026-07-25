"""
Plugin 1140: Race Condition Detection
======================================
Detects potential race conditions by sending concurrent requests to sensitive endpoints.
Real CVEs: CVE-2024-27198 (race condition), CVE-2023-36664
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class RaceConditionDetection(NaslPlugin):
    PLUGIN_ID = 1140
    NAME = 'Race Condition Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects potential race conditions by sending concurrent requests to '
        'sensitive endpoints (password reset, coupon redemption, account creation, '
        'transfer). Race conditions occur when timing gaps between check and use '
        'allow multiple operations to succeed when only one should.'
    )
    SOLUTION = (
        'Use database transactions with proper locking. Implement idempotency '
        'tokens. Use atomic operations for critical sections.'
    )
    CVE = ['CVE-2024-27198', 'CVE-2023-36664']
    PORTS = [80, 443, 8080, 8443]

    TARGET_PATHS = ['/api/reset-password', '/api/redeem-coupon', '/api/transfer', '/api/signup']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for path in self.TARGET_PATHS:
                try:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE

                    async def send_request() -> str:
                        r, w = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        host = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host = 'alieninc.tech'
                        req = (
                            f'POST {path} HTTP/1.1\r\n'
                            f'Host: {host}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Content-Type: application/json\r\n'
                            f'Content-Length: 0\r\n'
                            f'Connection: close\r\n\r\n'
                        )
                        w.write(req.encode())
                        await w.drain()
                        resp = b''
                        while True:
                            chunk = await asyncio.wait_for(r.read(4096), timeout=3)
                            if not chunk:
                                break
                            resp += chunk
                            if len(resp) > 32768:
                                break
                        w.close()
                        await w.wait_closed()
                        return resp.decode('utf-8', errors='ignore')

                    responses = await asyncio.gather(
                        *[send_request() for _ in range(5)], return_exceptions=True
                    )

                    success_count = 0
                    for resp in responses:
                        if isinstance(resp, str) and ('200' in resp.split('\r\n')[0] or '201' in resp.split('\r\n')[0]):
                            success_count += 1

                    if success_count > 1:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='high',
                            description=f'Potential race condition at {path}. {success_count}/5 concurrent requests succeeded.',
                            solution=self.SOLUTION,
                            evidence=f'Path: {path}, Concurrent successes: {success_count}/5',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2024-27198',
                                'https://portswigger.net/web-security/race-conditions',
                            ]
                        ))
                        return results

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
