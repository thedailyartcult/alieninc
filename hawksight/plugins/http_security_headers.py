"""
Plugin 1003: HTTP Security Headers Audit
==========================================
Checks for missing critical HTTP security headers.
Real CVEs: CVE-2024-38856 (clickjacking), CVE-2023-44487 (HTTP/2 rapid reset)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class HttpSecurityHeaders(NaslPlugin):
    PLUGIN_ID = 1003
    NAME = 'HTTP Security Headers Audit'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'The web server is missing one or more critical HTTP security headers. '
        'Missing headers can leave the application vulnerable to XSS, clickjacking, '
        'MIME sniffing, and protocol downgrade attacks.'
    )
    SOLUTION = (
        'Implement the following headers: Content-Security-Policy, X-Frame-Options, '
        'X-Content-Type-Options, Strict-Transport-Security, Referrer-Policy, '
        'Permissions-Policy, Cross-Origin-Opener-Policy.'
    )
    CVE = ['CVE-2024-38856', 'CVE-2023-44487']
    PORTS = [80, 443]

    REQUIRED_HEADERS = {
        'content-security-policy': ('CSP', 'critical'),
        'x-frame-options': ('X-Frame-Options', 'high'),
        'x-content-type-options': ('X-Content-Type-Options', 'medium'),
        'strict-transport-security': ('HSTS', 'high'),
        'referrer-policy': ('Referrer-Policy', 'medium'),
        'permissions-policy': ('Permissions-Policy', 'medium'),
        'cross-origin-opener-policy': ('COOP', 'medium'),
        'cross-origin-resource-policy': ('CORP', 'low'),
        'x-xss-protection': ('X-XSS-Protection', 'low'),
    }

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        results = []

        try:
            scheme = 'https' if port == 443 else 'http'
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Hawksight/1.0\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                if not chunk:
                    break
                response += chunk
                if len(response) > 16384:
                    break

            writer.close()
            await writer.wait_closed()

            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
            headers = {}
            for line in header_section.split('\r\n')[1:]:
                if ':' in line:
                    key, val = line.split(':', 1)
                    headers[key.strip().lower()] = val.strip()

            missing = []
            for header_name, (label, severity) in self.REQUIRED_HEADERS.items():
                if header_name not in headers:
                    missing.append((label, severity, header_name))

            if missing:
                desc_parts = [f'{m[0]} ({m[1]})' for m in missing]
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='medium',
                    description=f'Missing security headers: {", ".join(desc_parts)}',
                    solution=self.SOLUTION,
                    evidence=f'Server headers: {dict(list(headers.items())[:10])}',
                    references=[
                        'https://owasp.org/www-project-secure-headers/',
                        'https://nvd.nist.gov/vuln/detail/CVE-2024-38856',
                        'https://securityheaders.com/',
                    ]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='All required security headers present'
                ))

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'HTTP port {port} not reachable'
            ))

        return results
