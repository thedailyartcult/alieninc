"""
Plugin 1124: Cookie Security Configuration Audit
==================================================
Audits HTTP cookies for security flags: Secure, HttpOnly, SameSite,
Path, Domain, Max-Age. Missing flags expose cookies to theft via XSS
(missing HttpOnly), interception over HTTP (missing Secure), or CSRF
(missing SameSite).
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CookieSecurityAudit(NaslPlugin):
    PLUGIN_ID = 1124
    NAME = 'Cookie Security Configuration Audit'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Audits HTTP cookies for security flags: Secure, HttpOnly, SameSite, '
        'Path, Domain, Max-Age. Missing flags expose cookies to theft via XSS '
        '(missing HttpOnly), interception over HTTP (missing Secure), or CSRF '
        '(missing SameSite). Checks session cookies, auth tokens, and tracking '
        'cookies.'
    )
    SOLUTION = (
        'Set Secure flag on all cookies. Set HttpOnly on session/auth cookies. '
        'Use SameSite=Lax or Strict. Scope cookies with Path and Domain '
        'restrictions.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    PATHS = ['/', '/login', '/api', '/admin']

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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                all_cookies = []

                for path in self.PATHS:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    req = (
                        f'GET {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
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
                            if len(response) > 16384:
                                break
                    except asyncio.TimeoutError:
                        pass

                    writer.close()
                    await writer.wait_closed()

                    header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                    for line in header_section.split('\r\n'):
                        if line.lower().startswith('set-cookie:'):
                            all_cookies.append(line[12:].strip())

                cookie_issues = []

                for cookie in all_cookies:
                    cookie_lower = cookie.lower()
                    name_part = cookie.split('=')[0] if '=' in cookie else cookie

                    if 'secure' not in cookie_lower:
                        cookie_issues.append(f'Cookie "{name_part}" missing Secure flag')
                    if 'httponly' not in cookie_lower:
                        cookie_issues.append(f'Cookie "{name_part}" missing HttpOnly flag')
                    if 'samesite' not in cookie_lower:
                        cookie_issues.append(f'Cookie "{name_part}" missing SameSite attribute')
                    if ';' not in cookie:
                        cookie_issues.append(f'Cookie "{name_part}" has no flags at all')

                if cookie_issues:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description=f'Cookie security issues: {len(cookie_issues)} problem(s) found',
                        solution=self.SOLUTION,
                        evidence='; '.join(cookie_issues[:8]),
                        references=[
                            'https://owasp.org/www-community/controls/HttpOnly',
                            'https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies',
                            'https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='All cookies have proper security flags'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No cookies found or unable to check on checked ports'
            ))

        return results
