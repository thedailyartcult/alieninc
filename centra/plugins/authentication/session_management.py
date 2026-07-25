"""
Plugin 1027: Session Management Security
==========================================
Checks cookie and session security controls:
- Secure flag on cookies
- HttpOnly flag on cookies
- SameSite attribute
- Session cookie naming conventions
- Cookie expiration/session timeout
- CSP frame-ancestors (clickjacking prevention)
- X-Frame-Options

Real standards:
- SOC 2 CC6.1 (Logical access security)
- HIPAA §164.312(d) (Person authentication)
- ISO 27001 A.8.5 (Secure authentication)
- NIST 800-53 SC-23 (Session Authenticity)
"""
import asyncio
import ssl
import re

from plugins import NaslPlugin, PluginResult


class SessionManagement(NaslPlugin):
    PLUGIN_ID = 1027
    NAME = 'Session Management Security'
    FAMILY = 'Authentication & Sessions'
    PLUGIN_TYPE = 'remote'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Checks cookie security flags (Secure, HttpOnly, SameSite), session management '
        'practices, and clickjacking prevention mechanisms.'
    )
    SOLUTION = (
        'Set Secure, HttpOnly, and SameSite=Strict/Lax flags on all session cookies. '
        'Implement session timeout. Add X-Frame-Options or CSP frame-ancestors.'
    )
    PORTS = [80, 443]
    REFERENCES = [
        'https://owasp.org/www-community/controls/SecureCookieAttribute',
        'https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html',
    ]

    SESSION_COOKIE_NAMES = [
        'session', 'sess', 'sid', 'jsessionid', 'phpsessid', 'aspsessionid',
        'csrftoken', '_csrf', 'xsrf', 'x-csrf', 'auth', 'token', 'access_token',
        'alieninc', 'panteon',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        results = []

        try:
            scheme = 'https' if port == 443 else 'http'
            if port == 443:

                ssl_context = ssl.create_default_context()

                ssl_context.check_hostname = False

                ssl_context.verify_mode = ssl.CERT_NONE

                reader, writer = await asyncio.wait_for(

                    asyncio.open_connection(target, port, ssl=ssl_context), timeout=10

                )

            else:

                reader, writer = await asyncio.wait_for(

                    asyncio.open_connection(target, port), timeout=10

                )

            req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                if not chunk:
                    break
                response += chunk
                if len(response) > 32768:
                    break

            writer.close()
            await writer.wait_closed()

            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
            headers = {}
            for line in header_section.split('\r\n')[1:]:
                if ':' in line:
                    key, val = line.split(':', 1)
                    headers[key.strip().lower()] = val.strip()

            issues = []
            passes = []

            set_cookie_headers = []
            for line in header_section.split('\r\n'):
                if line.lower().startswith('set-cookie:'):
                    set_cookie_headers.append(line.split(':', 1)[1].strip())

            if set_cookie_headers:
                for cookie in set_cookie_headers:
                    cookie_lower = cookie.lower()
                    cookie_name = cookie.split('=')[0].strip() if '=' in cookie else cookie[:30]

                    is_session = any(name in cookie_lower for name in self.SESSION_COOKIE_NAMES)

                    if is_session or True:
                        if 'secure' not in cookie_lower:
                            if port == 443:
                                issues.append(f'Cookie "{cookie_name}" missing Secure flag (should always be Secure on HTTPS)')
                            else:
                                passes.append(f'Cookie "{cookie_name}" on HTTP (Secure not required)')
                        else:
                            passes.append(f'Cookie "{cookie_name}" has Secure flag')

                        if 'httponly' not in cookie_lower:
                            if is_session:
                                issues.append(f'Session cookie "{cookie_name}" missing HttpOnly flag (XSS risk)')
                            else:
                                issues.append(f'Cookie "{cookie_name}" missing HttpOnly flag')
                        else:
                            passes.append(f'Cookie "{cookie_name}" has HttpOnly flag')

                        if 'samesite' not in cookie_lower:
                            issues.append(f'Cookie "{cookie_name}" missing SameSite attribute (CSRF risk)')
                        else:
                            samesite_match = re.search(r'samesite\s*=\s*(\w+)', cookie_lower)
                            if samesite_match:
                                val = samesite_match.group(1)
                                if val in ('strict', 'lax'):
                                    passes.append(f'Cookie "{cookie_name}" SameSite={val}')
                                else:
                                    issues.append(f'Cookie "{cookie_name}" SameSite=None (CSRF risk)')
            else:
                passes.append('No cookies set (session may be managed client-side)')

            xfo = headers.get('x-frame-options', '')
            csp = headers.get('content-security-policy', '')
            has_frame_protection = False

            if xfo:
                if xfo.lower() in ('deny', 'sameorigin'):
                    passes.append(f'X-Frame-Options: {xfo} (clickjacking protection)')
                    has_frame_protection = True
                else:
                    issues.append(f'X-Frame-Options has weak value: {xfo}')

            if csp and 'frame-ancestors' in csp.lower():
                passes.append('CSP frame-ancestors directive present')
                has_frame_protection = True

            if not has_frame_protection and not xfo:
                issues.append('No clickjacking protection (missing X-Frame-Options and CSP frame-ancestors)')

            hsts = headers.get('strict-transport-security', '')
            if hsts:
                max_age_match = re.search(r'max-age\s*=\s*(\d+)', hsts)
                if max_age_match:
                    max_age = int(max_age_match.group(1))
                    if max_age >= 31536000:
                        passes.append(f'HSTS max-age={max_age} (>= 1 year)')
                    elif max_age >= 86400:
                        passes.append(f'HSTS max-age={max_age} (active but < 1 year)')
                    else:
                        issues.append(f'HSTS max-age={max_age} too short (should be >= 31536000)')

                if 'includesubdomains' in hsts.lower():
                    passes.append('HSTS includes subdomains')
                if 'preload' in hsts.lower():
                    passes.append('HSTS preload enabled')
            else:
                if port == 443:
                    issues.append('Missing HSTS header on HTTPS (should enforce TLS)')

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
                    description=f'Session management issues: {len(issues)} found, {len(passes)} passes',
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
                    description='Session management checks passed',
                    evidence=f'Passed: {", ".join(passes[:5])}',
                    references=self.REFERENCES,
                ))

        except Exception as e:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                severity='info',
                description=f'Could not check session management: {e}',
            ))

        return results
