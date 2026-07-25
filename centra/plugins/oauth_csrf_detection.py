import asyncio
import ssl
import urllib.parse
from plugins import NaslPlugin, PluginResult


class OauthCsrfDetection(NaslPlugin):
    PLUGIN_ID = 1218
    NAME = 'OAuth CSRF / State Parameter Validation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects OAuth CSRF vulnerabilities caused by missing or predictable state parameter in OAuth flows. Without a random state parameter, attackers can initiate CSRF attacks by tricking users into clicking a crafted OAuth authorization URL, linking the attacker's account to the victim."
    SOLUTION = 'Always use a cryptographically random state parameter in OAuth requests. Validate the state parameter on callback. Bind state to the user session.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    OAUTH_PATHS = [
        '/oauth/authorize', '/auth/login', '/api/auth/oauth',
        '/oauth2/authorize', '/auth/oauth', '/api/oauth/authorize',
        '/auth/authorize', '/api/auth/callback', '/oauth/callback',
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

                for path in self.OAUTH_PATHS:
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
                            lower_body = body.lower()
                            if 'oauth' in lower_body or 'authorize' in lower_body or 'callback' in lower_body:
                                if 'state' in body:
                                    state_start = body.find('state=')
                                    if state_start >= 0:
                                        state_val = body[state_start + 6:state_start + 60]
                                        state_val = urllib.parse.unquote(state_val.split('&')[0].split('"')[0].split("'")[0])
                                        if state_val.lower() in ('', 'none', 'null', 'undefined', '0', '1', 'true'):
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='high',
                                                description=f'OAuth endpoint {path} has empty or predictable state parameter: "{state_val}"',
                                                solution=self.SOLUTION,
                                                evidence=f'State value: "{state_val}" on {path}',
                                                references=[
                                                    'https://owasp.org/www-community/attacks/CSRF',
                                                    'https://datatracker.ietf.org/doc/html/rfc6749#section-10.12',
                                                ]
                                            ))
                                        elif len(state_val) < 8:
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=6.5,
                                                severity='medium',
                                                description=f'OAuth endpoint {path} has short state parameter ({len(state_val)} chars)',
                                                solution=self.SOLUTION,
                                                evidence=f'State value: "{state_val}" length: {len(state_val)} on {path}',
                                                references=[
                                                    'https://owasp.org/www-community/attacks/CSRF',
                                                    'https://datatracker.ietf.org/doc/html/rfc6749#section-10.12',
                                                ]
                                            ))
                                    else:
                                        results.append(PluginResult(
                                            vulnerable=True,
                                            target=target,
                                            port=port_to_check,
                                            cvss_score=self.CVSS_SCORE,
                                            severity='high',
                                            description=f'OAuth endpoint {path} is missing state parameter in response',
                                            solution=self.SOLUTION,
                                            evidence=f'No state parameter found in response from {path}',
                                            references=[
                                                'https://owasp.org/www-community/attacks/CSRF',
                                                'https://datatracker.ietf.org/doc/html/rfc6749#section-10.12',
                                            ]
                                        ))
                                else:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=f'OAuth endpoint {path} is missing state parameter entirely',
                                        solution=self.SOLUTION,
                                        evidence=f'No state parameter found in response from {path}',
                                        references=[
                                            'https://owasp.org/www-community/attacks/CSRF',
                                            'https://datatracker.ietf.org/doc/html/rfc6749#section-10.12',
                                        ]
                                    ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No OAuth CSRF vulnerabilities detected'))
        return results
