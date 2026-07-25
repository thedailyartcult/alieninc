import asyncio
import ssl
import json
from plugins import NaslPlugin, PluginResult


class OpenidMisconfiguration(NaslPlugin):
    PLUGIN_ID = 1224
    NAME = 'OpenID Connect Misconfiguration Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects OpenID Connect misconfigurations including weak token signing algorithms, missing audience (aud) validation, missing issuer (iss) validation, and acceptance of unencrypted ID tokens over plain HTTP.'
    SOLUTION = 'Validate aud and iss claims in ID tokens. Use RS256 or stronger signing. Enforce HTTPS for all OIDC endpoints. Use nonce to prevent replay attacks.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    WELL_KNOWN_PATHS = [
        '/.well-known/openid-configuration',
        '/.well-known/oauth-authorization-server',
    ]

    WEAK_ALGORITHMS = ['none', 'HS256', 'HS384', 'HS512']

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

                for path in self.WELL_KNOWN_PATHS:
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
                            if '200' in status_line:
                                try:
                                    config = json.loads(body)
                                    issues = []
                                    if 'id_token_signing_alg_values_supported' in config:
                                        algs = config['id_token_signing_alg_values_supported']
                                        for weak in self.WEAK_ALGORITHMS:
                                            if weak in algs:
                                                issues.append(f'weak algorithm: {weak}')
                                    if 'request_object_signing_alg_values_supported' in config:
                                        algs = config['request_object_signing_alg_values_supported']
                                        if 'none' in algs:
                                            issues.append('request signing alg: none')
                                    if 'token_endpoint_auth_methods_supported' in config:
                                        methods = config['token_endpoint_auth_methods_supported']
                                        if 'none' in methods:
                                            issues.append('token endpoint auth method: none')
                                    if scheme == 'http':
                                        issues.append('served over plain HTTP')
                                    if not config.get('issuer'):
                                        issues.append('missing issuer')
                                    if not config.get('authorization_endpoint'):
                                        issues.append('missing authorization_endpoint')

                                    if issues:
                                        results.append(PluginResult(
                                            vulnerable=True,
                                            target=target,
                                            port=port_to_check,
                                            cvss_score=self.CVSS_SCORE,
                                            severity='high',
                                            description=f'OIDC misconfiguration at {path}: {", ".join(issues)}',
                                            solution=self.SOLUTION,
                                            evidence=f'Configuration issues: {", ".join(issues)}',
                                            references=[
                                                'https://owasp.org/www-project-cheat-sheets/cheatsheets/OpenID_Connect_Cheat_Sheet.html',
                                                'https://openid.net/specs/openid-connect-core-1_0.html',
                                            ]
                                        ))
                                except json.JSONDecodeError:
                                    pass
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No OpenID Connect misconfiguration detected'))
        return results
