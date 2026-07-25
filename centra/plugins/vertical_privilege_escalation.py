import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class VerticalPrivilegeEscalation(NaslPlugin):
    PLUGIN_ID = 1222
    NAME = 'Vertical Privilege Escalation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = 'Detects vertical privilege escalation vulnerabilities where a low-privileged user can access admin or high-privilege functions. Tests by accessing admin endpoints, hidden menus, and privileged API routes directly without proper authorization.'
    SOLUTION = 'Implement role-based access control (RBAC) on every endpoint. Use middleware to enforce authorization. Never rely on UI hiding for security. Verify admin actions require re-authentication.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    ADMIN_PATHS = [
        '/admin', '/api/admin', '/dashboard', '/manage', '/console',
        '/api/internal', '/supervisor', '/admin/dashboard', '/admin/users',
        '/admin/settings', '/admin/config', '/admin/api', '/api/manage',
        '/api/console', '/api/supervisor', '/api/dashboard',
        '/admin/panel', '/admin/console', '/api/admin/users',
        '/api/admin/settings', '/api/admin/config',
        '/administrator', '/api/administrator',
        '/backend', '/api/backend', '/internal', '/api/internal/admin',
        '/admin/user', '/admin/role', '/api/admin/role',
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

                for path in self.ADMIN_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        req = (
                            f'GET {path} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
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
                        writer.close()
                        await writer.wait_closed()

                        if response:
                            status_line = response.split(b'\r\n', 1)[0].decode(errors='ignore')
                            body = response.split(b'\r\n\r\n', 1)[1].decode(errors='ignore') if b'\r\n\r\n' in response else ''
                            if '200' in status_line or '201' in status_line:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'Admin endpoint accessible without authentication: {path}',
                                    solution=self.SOLUTION,
                                    evidence=f'Path: {path} returned {status_line.strip()}',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Forced_browsing',
                                        'https://portswigger.net/web-security/access-control/privilege-escalation',
                                    ]
                                ))
                                break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No vertical privilege escalation detected'))
        return results
