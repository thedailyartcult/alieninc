"""
Plugin 1051: NIST 800-53 AC-7 — Unsuccessful Login Attempts Check
====================================================================
Tests whether login endpoints enforce account lockout after repeated
failed attempts, as required by NIST SP 800-53 AC-7.
Real references: NIST SP 800-53 Rev.5 AC-7
"""
import asyncio
import time

from plugins import NaslPlugin, PluginResult


class NistLockoutCheck(NaslPlugin):
    PLUGIN_ID = 1051
    NAME = 'NIST 800-53 AC-7 — Unsuccessful Login Attempts'
    FAMILY = 'Authentication & Access Control'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks if the web application enforces account lockout after '
        'repeated failed login attempts, as required by NIST SP 800-53 AC-7. '
        'Absence of lockout enables brute-force password attacks.'
    )
    SOLUTION = (
        'Implement account lockout after 3-5 failed attempts per NIST SP 800-53 AC-7. '
        'Use progressive delays. Implement CAPTCHA after repeated failures. '
        'Log all authentication failures. Alert on brute-force patterns.'
    )
    PORTS = [80, 443]
    CVE = ['CVE-2023-41350', 'CVE-2024-23943']

    LOGIN_ENDPOINTS = [
        '/login',
        '/api/login',
        '/auth',
        '/api/auth',
        '/signin',
        '/api/v1/login',
        '/user/login',
        '/admin/login',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        tested_any = False

        for endpoint in self.LOGIN_ENDPOINTS:
            result = await self._test_lockout(target, port, endpoint)
            if result is not None:
                tested_any = True
                if result:
                    return result

        if not tested_any:
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 severity='info',
                                 description='No login endpoints found to test')]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='All tested login endpoints appear to have lockout or rate limiting'
        )]

    async def _test_lockout(self, target: str, port: int,
                            endpoint: str) -> PluginResult | None:
        first_response = None
        last_response = None
        attempt_times = []

        for attempt in range(6):
            try:
                start = time.monotonic()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )

                body = b'username=admin&password=wrongpass' + str(attempt).encode()
                req = (
                    f'POST {endpoint} HTTP/1.1\r\n'
                    f'Host: {target}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Content-Type: application/x-www-form-urlencoded\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'Connection: close\r\n\r\n'
                )
                writer.write(req.encode() + body)
                await writer.drain()

                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(2048), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 4096:
                        break

                elapsed = time.monotonic() - start
                attempt_times.append(elapsed)

                writer.close()
                await writer.wait_closed()

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                headers_lower = header_section.lower()

                if 'retry-after' in headers_lower or '429' in header_section:
                    for h_line in header_section.split('\r\n'):
                        if 'retry-after' in h_line.lower():
                            return PluginResult(
                                vulnerable=False, target=target, port=port,
                                description=f'Rate limiting detected on {endpoint} (Retry-After header)'
                            )
                    return PluginResult(
                        vulnerable=False, target=target, port=port,
                        description=f'Rate limiting (429) detected on {endpoint}'
                    )

                if attempt == 0:
                    first_response = len(response)
                last_response = len(response)

                if response:
                    body_start = response.find(b'\r\n\r\n')
                    body_text = response[body_start:].decode('utf-8', errors='ignore') if body_start > 0 else ''

                    if 'too many' in body_text.lower() or 'locked' in body_text.lower() or \
                       'blocked' in body_text.lower() or 'suspended' in body_text.lower() or \
                       'rate limit' in body_text.lower() or '429' in body_text:
                        return PluginResult(
                            vulnerable=False, target=target, port=port,
                            description=f'Lockout or rate limiting message detected on {endpoint}'
                        )

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                return None

        if len(attempt_times) >= 4:
            later_attempts = attempt_times[-3:]
            earliest = attempt_times[0]
            avg_later = sum(later_attempts) / len(later_attempts)
            max_diff = max(attempt_times) - min(attempt_times)

            if max_diff > 2.0 and avg_later > earliest * 1.5:
                return PluginResult(
                    vulnerable=False, target=target, port=port,
                    description=f'Progressive delay detected on {endpoint} — effective lockout'
                )

        return PluginResult(
            vulnerable=True,
            target=target,
            port=port,
            cvss_score=self.CVSS_SCORE,
            severity='medium',
            description=f'No account lockout detected on {endpoint} — 6 attempts all accepted',
            solution=self.SOLUTION,
            evidence=f'Endpoint {endpoint} accepted 6 failed attempts without lockout or rate limiting',
            references=[
                'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                'https://csrc.nist.gov/glossary/term/ac-7',
            ]
        )
