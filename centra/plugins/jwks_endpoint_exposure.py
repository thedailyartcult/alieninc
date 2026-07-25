import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class JwksEndpointExposure(NaslPlugin):
    PLUGIN_ID = 1204
    NAME = 'JWKS Endpoint Key Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Detects exposed JWKS (JSON Web Key Set) endpoints that reveal public keys used for JWT verification. While public keys are meant to be public, their exposure through predictable paths allows attackers to identify the key type, size, and algorithm for targeted attacks.'
    SOLUTION = 'Use non-guessable JWKS endpoint paths. Restrict access to JWKS endpoints using rate limiting. Consider using OAuth Discovery URL instead of exposing raw keys.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    JWKS_PATHS = [
        '/.well-known/jwks.json',
        '/jwks',
        '/api/jwks',
        '/.well-known/openid-configuration',
        '/oauth/jwks',
        '/auth/jwks',
        '/.well-known/jwks',
        '/jwks.json',
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

                for path in self.JWKS_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host_header = 'alieninc.tech'

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()

                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk: break
                                response += chunk
                                if len(response) > 8192: break
                        except asyncio.TimeoutError:
                            pass

                        writer.close()
                        await writer.wait_closed()

                        if response:
                            header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else b''
                            status_line = header_section.split(b'\r\n')[0].decode('utf-8', errors='ignore') if header_section else ''
                            status_code = 0
                            parts = status_line.split(' ')
                            if len(parts) >= 2:
                                try:
                                    status_code = int(parts[1])
                                except ValueError:
                                    pass

                            if status_code == 200:
                                body = response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in response else response
                                body_str = body.decode('utf-8', errors='ignore')

                                jwks_indicators = ['"keys"', '"kty"', '"use"', '"alg"', '"n"', '"e"', '"kid"']
                                oidc_indicators = ['"issuer"', '"authorization_endpoint"', '"token_endpoint"', '"jwks_uri"']

                                has_jwks = all(ind in body_str for ind in ['"keys"', '"kty"'])
                                has_oidc = any(ind in body_str for ind in oidc_indicators)

                                if has_jwks:
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='medium',
                                        description=f'JWKS endpoint exposed at {path} - public keys revealed',
                                        solution=self.SOLUTION,
                                        evidence=f'Path: {path}, response contains key material (kty, keys)',
                                        references=['https://owasp.org/www-community/vulnerabilities/JWT_Key_Exposure']
                                    ))
                                elif has_oidc and path == '/.well-known/openid-configuration':
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='medium',
                                        description=f'OpenID Connect discovery document exposed at {path}',
                                        solution=self.SOLUTION,
                                        evidence=f'Path: {path}, OpenID Connect configuration exposed',
                                        references=['https://openid.net/specs/openid-connect-discovery-1_0.html']
                                    ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No JWKS endpoint exposure detected'))
        return results
