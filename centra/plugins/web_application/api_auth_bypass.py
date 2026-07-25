import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class ApiAuthBypassDetection(NaslPlugin):
    PLUGIN_ID = 1225
    NAME = 'API Authentication Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = 'Detects API authentication bypass vulnerabilities by testing unauthenticated access to API endpoints that should require authentication. Tests with missing Authorization headers, empty tokens, null tokens, and expired tokens.'
    SOLUTION = 'Validate authentication on every API endpoint. Use a middleware-based auth system. Return consistent 401 responses. Never expose internal API endpoints without auth.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    API_PATHS = [
        '/api/admin', '/api/user', '/api/users', '/api/profile',
        '/api/settings', '/api/config', '/api/data', '/api/status',
        '/api/admin/users', '/api/admin/settings', '/api/admin/config',
        '/api/v1/admin', '/api/v1/user', '/api/v1/users',
        '/api/v1/profile', '/api/v1/settings', '/api/v1/data',
        '/api/v2/admin', '/api/v2/user', '/api/v2/users',
        '/api/internal', '/api/private', '/api/secure',
        '/api/account', '/api/orders', '/api/payments',
        '/api/transactions', '/api/reports', '/api/analytics',
    ]

    AUTH_HEADERS = [
        (None, None),
        ('Authorization', ''),
        ('Authorization', 'Bearer'),
        ('Authorization', 'Bearer '),
        ('Authorization', 'Bearer null'),
        ('Authorization', 'Bearer undefined'),
        ('Authorization', 'Bearer 0'),
        ('Authorization', 'Bearer false'),
        ('Authorization', 'Bearer invalid-token-here'),
        ('Authorization', 'Token null'),
        ('Authorization', 'Token undefined'),
        ('X-Auth-Token', 'null'),
        ('X-Auth-Token', 'undefined'),
        ('X-API-Key', 'null'),
        ('X-API-Key', 'undefined'),
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

                for path in self.API_PATHS:
                    for auth_header_name, auth_header_value in self.AUTH_HEADERS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\n'
                            if auth_header_name:
                                req += f'{auth_header_name}: {auth_header_value}\r\n'
                            req += 'Connection: close\r\n\r\n'

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
                            writer.close()
                            await writer.wait_closed()

                            if response:
                                status_line = response.split(b'\r\n', 1)[0].decode(errors='ignore')
                                body = response.split(b'\r\n\r\n', 1)[1].decode(errors='ignore') if b'\r\n\r\n' in response else ''
                                if '200' in status_line or '201' in status_line:
                                    auth_desc = f'no auth header' if auth_header_name is None else f'auth: {auth_header_name}: {auth_header_value}'
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'API auth bypass on {path} with {auth_desc}',
                                        solution=self.SOLUTION,
                                        evidence=f'Path: {path}, {auth_desc}, returned {status_line.strip()}',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Authentication_Bypass',
                                            'https://portswigger.net/web-security/authentication',
                                        ]
                                    ))
                                    break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No API auth bypass detected'))
        return results
