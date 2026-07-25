"""
Plugin 1163: NIST AC-3 Access Enforcement Check
=================================================
Checks NIST SP 800-53 AC-3 (Access Enforcement) compliance by verifying
that the application enforces authorized access to protected resources.
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class NistAc3Detection(NaslPlugin):
    PLUGIN_ID = 1163
    NAME = 'NIST AC-3 Access Enforcement Check'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Checks NIST SP 800-53 AC-3 (Access Enforcement) compliance by verifying '
        'that the application enforces authorized access to protected resources. '
        'Tests for proper authentication on admin/sensitive endpoints and '
        'appropriate authorization controls.'
    )
    SOLUTION = (
        'Implement mandatory access controls on all resources. Use role-based '
        'access control (RBAC). Ensure all sensitive endpoints require authentication.'
    )
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATHS = [
        '/admin', '/administrator', '/wp-admin', '/dashboard',
        '/admin/login', '/api/admin', '/manage', '/management',
        '/console', '/api/users', '/api/config', '/api/settings',
        '/config', '/setup', '/install', '/api/keys',
        '/api/tokens', '/debug', '/api/debug', '/api/internal',
        '/api/v1/admin', '/api/v2/admin', '/api/health',
        '/.env', '/backup', '/api/backup', '/logs',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            unprotected = []

            for path in self.SENSITIVE_PATHS:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check), timeout=5
                    )
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'
                    req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 8192:
                            break
                    writer.close()
                    await writer.wait_closed()

                    status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                    body = response.split(b'\r\n\r\n', 1)
                    body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                    if '200' in status_line or '201' in status_line:
                        login_indicators = [
                            'login', 'sign in', 'password', 'authenticate',
                            'unauthorized', 'forbidden', 'access denied',
                            '401', '403',
                        ]
                        has_auth_ui = any(ind in body_text.lower() for ind in login_indicators)

                        if not has_auth_ui:
                            unprotected.append(path)
                    elif '301' in status_line or '302' in status_line or '307' in status_line:
                        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                        headers = {}
                        for line in header_section.split('\r\n')[1:]:
                            if ':' in line:
                                key, val = line.split(':', 1)
                                headers[key.strip().lower()] = val.strip()
                        location = headers.get('location', '')
                        if 'login' not in location.lower() and 'auth' not in location.lower():
                            unprotected.append(path)

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    pass

            if unprotected:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=port_to_check,
                    cvss_score=self.CVSS_SCORE, severity='medium',
                    description=f'Sensitive endpoints accessible without authentication: {len(unprotected)} found',
                    solution=self.SOLUTION,
                    evidence=f'Unprotected paths: {", ".join(unprotected[:10])}',
                    references=[
                        'https://csrc.nist.gov/Projects/risk-management/sp800-53-controls/release-search#/control?version=5.1&number=AC-3',
                        'https://www.tenable.com/plugins/nessus/109343',
                    ]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='All sensitive endpoints require authentication — NIST AC-3 compliant',
                    evidence='No unprotected sensitive paths detected'
                ))

        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
