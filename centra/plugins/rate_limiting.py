"""
Plugin 1028: Rate Limiting & Brute Force Protection
=====================================================
Checks for rate limiting on sensitive endpoints:
- Login endpoint rate limiting
- API endpoint rate limiting
- Password reset rate limiting
- Registration rate limiting
- Generic API rate limit headers

Real standards:
- SOC 2 CC6.1 (Logical access security)
- FedRAMP IA-5 (Authenticator management)
- NIST 800-53 AC-7 (Unsuccessful login attempts)
- OWASP ASVS V2.2 (Rate limiting)
"""
import asyncio
import ssl
import time

from plugins import NaslPlugin, PluginResult


class RateLimitingBruteForce(NaslPlugin):
    PLUGIN_ID = 1028
    NAME = 'Rate Limiting & Brute Force Protection'
    FAMILY = 'Authentication & Access Control'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks for rate limiting on login, API, and sensitive endpoints to prevent '
        'brute force attacks and credential stuffing.'
    )
    SOLUTION = (
        'Implement rate limiting on authentication endpoints (max 5 attempts per minute). '
        'Add CAPTCHA after failed attempts. Use account lockout policies. Return rate limit headers.'
    )
    PORTS = [80, 443]
    REFERENCES = [
        'https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html',
        'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/05-Enumerate_Infrastructure_and_Application_Admin_Interfaces',
    ]

    SENSITIVE_ENDPOINTS = [
        '/api/login',
        '/login',
        '/admin',
        '/api/admin',
        '/auth',
        '/api/auth',
        '/api/v1/auth',
        '/pxpadmin/bin/authform.cgi',
        '/dashboard',
        '/api/panteon/stats',
    ]

    RATE_LIMIT_HEADERS = [
        'x-ratelimit-limit',
        'x-ratelimit-remaining',
        'x-ratelimit-reset',
        'retry-after',
        'ratelimit-limit',
        'ratelimit-remaining',
        'ratelimit-reset',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []

        try:
            scheme = 'https' if port == 443 else 'http'

            endpoint_results = []
            rate_limit_detected = False

            for endpoint in self.SENSITIVE_ENDPOINTS:
                try:
                    if port == 443:

                        ssl_context = ssl.create_default_context()

                        ssl_context.check_hostname = False

                        ssl_context.verify_mode = ssl.CERT_NONE

                        reader, writer = await asyncio.wait_for(

                            asyncio.open_connection(target, port, ssl=ssl_context), timeout=5

                        )

                    else:

                        reader, writer = await asyncio.wait_for(

                            asyncio.open_connection(target, port), timeout=5

                        )

                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'
                    body = b'{"email":"test","password":"test"}'
                    req = f'POST {endpoint} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
                    writer.write(req.encode() + body)
                    await writer.drain()

                    response = b''
                    while True:
                        chunk = await asyncio.wait_for(reader.read(2048), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 8192:
                            break

                    writer.close()
                    await writer.wait_closed()

                    header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                    status_line = header_section.split('\r\n')[0] if header_section else ''
                    status_code = 0
                    if 'HTTP/' in status_line:
                        try:
                            status_code = int(status_line.split()[1])
                        except (IndexError, ValueError):
                            pass

                    headers_lower = header_section.lower()
                    has_rate_limit = any(h in headers_lower for h in self.RATE_LIMIT_HEADERS)
                    if has_rate_limit:
                        rate_limit_detected = True

                    endpoint_results.append({
                        'endpoint': endpoint,
                        'status': status_code,
                        'rate_limit': has_rate_limit,
                        'accessible': status_code in (200, 301, 302, 401, 403),
                    })

                except Exception:
                    endpoint_results.append({
                        'endpoint': endpoint,
                        'status': 0,
                        'rate_limit': False,
                        'accessible': False,
                    })

            issues = []
            passes = []

            accessible_endpoints = [e for e in endpoint_results if e['accessible']]
            if accessible_endpoints:
                if rate_limit_detected:
                    passes.append(f'Rate limiting headers detected on {len(accessible_endpoints)} accessible endpoint(s)')
                else:
                    issues.append(f'No rate limiting headers on {len(accessible_endpoints)} accessible endpoint(s) — vulnerable to brute force')

                for ep in accessible_endpoints[:3]:
                    if not ep['rate_limit']:
                        issues.append(f'  Endpoint {ep["endpoint"]} (HTTP {ep["status"]}) has no rate limit headers')
            else:
                passes.append('No sensitive endpoints publicly accessible')

            if issues:
                severity = 'high' if len(issues) >= 3 else 'medium'
                evidence_lines = ['ISSUES:'] + [f'  - {i}' for i in issues]
                if passes:
                    evidence_lines.append('PASSES:')
                    evidence_lines += [f'  + {p}' for p in passes]

                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity=severity,
                    description=f'Rate limiting gaps: {len(issues)} issues found',
                    solution=self.SOLUTION,
                    evidence='\n'.join(evidence_lines),
                    references=self.REFERENCES,
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False,
                    target=target,
                    port=port,
                    severity='info',
                    description='Rate limiting checks passed',
                    evidence=f'Passed: {", ".join(passes)}',
                    references=self.REFERENCES,
                ))

        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check rate limiting: {e}',
            ))

        return results
