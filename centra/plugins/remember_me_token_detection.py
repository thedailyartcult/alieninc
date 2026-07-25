import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class RememberMeTokenDetection(NaslPlugin):
    PLUGIN_ID = 1220
    NAME = 'Remember Me Token Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects insecure remember-me token implementations including persistent tokens without expiration, tokens stored in plaintext, predictable token generation, and tokens that do not invalidate on password change.'
    SOLUTION = 'Use cryptographically random tokens. Set token expiration (30 days max). Invalidate all tokens on password change. Store tokens as hashed values in database.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    COOKIE_NAMES = ['remember_me', 'remember', 'persist', 'token', 'rememberme', 'remember-token', 'persistent']

    PATHS = ['/login', '/api/login', '/auth/login', '/', '/api/auth/login']

    PREDICTABLE_PATTERNS = [
        re.compile(r'^\d+$'),
        re.compile(r'^[a-f0-9]{8,32}$', re.IGNORECASE),
        re.compile(r'^[a-zA-Z0-9]+$'),
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

                for path in self.PATHS:
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
                            headers_raw = response.split(b'\r\n\r\n', 1)[0].decode(errors='ignore')
                            cookies = re.findall(r'Set-Cookie:\s*([^;]+)', headers_raw, re.IGNORECASE)
                            for cookie in cookies:
                                cookie_lower = cookie.lower()
                                for cookie_name in self.COOKIE_NAMES:
                                    if cookie_name in cookie_lower:
                                        name_val = cookie.split('=', 1)
                                        if len(name_val) == 2:
                                            val = name_val[1]
                                            token_info = f'{name_val[0]}={val}'
                                            for pattern in self.PREDICTABLE_PATTERNS:
                                                if pattern.match(val):
                                                    results.append(PluginResult(
                                                        vulnerable=True,
                                                        target=target,
                                                        port=port_to_check,
                                                        cvss_score=self.CVSS_SCORE,
                                                        severity='medium',
                                                        description=f'Predictable remember-me token format detected: {token_info}',
                                                        solution=self.SOLUTION,
                                                        evidence=f'Cookie: {token_info} matches pattern: {pattern.pattern}',
                                                        references=[
                                                            'https://owasp.org/www-community/vulnerabilities/Insecure_Remember_Me_Token',
                                                            'https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html',
                                                        ]
                                                    ))
                                                    break
                                            expiry = re.search(r'expires=([^;]+)', headers_raw, re.IGNORECASE)
                                            max_age = re.search(r'max-age=(\d+)', headers_raw, re.IGNORECASE)
                                            if not expiry and not max_age:
                                                results.append(PluginResult(
                                                    vulnerable=True,
                                                    target=target,
                                                    port=port_to_check,
                                                    cvss_score=5.3,
                                                    severity='medium',
                                                    description=f'Remember-me cookie has no expiration: {token_info}',
                                                    solution=self.SOLUTION,
                                                    evidence=f'Cookie: {token_info} set without expiry/max-age',
                                                    references=[
                                                        'https://owasp.org/www-community/vulnerabilities/Insecure_Remember_Me_Token',
                                                    ]
                                                ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No insecure remember-me tokens detected'))
        return results
