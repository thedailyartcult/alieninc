"""
Plugin 1184: Insecure Password Reset Detection
================================================
Detects insecure password reset implementations including predictable
reset tokens, tokens in URLs, long-lived tokens, and missing token
expiration.
"""
import asyncio
import re
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class PasswordResetInsecurity(NaslPlugin):
    PLUGIN_ID = 1184
    NAME = 'Insecure Password Reset Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects insecure password reset implementations including predictable '
        'reset tokens, tokens in URLs, long-lived tokens, and missing token '
        'expiration. Analyzes password reset flow for security weaknesses.'
    )
    SOLUTION = (
        'Use cryptographically random reset tokens. Set short token expiration '
        '(15-30 min). Invalidate tokens after use. Require user interaction to '
        'confirm reset (email/phone). Never include tokens in URLs.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    RESET_ENDPOINTS = [
        '/forgot-password',
        '/reset-password',
        '/api/auth/reset',
        '/api/forgot-password',
        '/api/reset-password',
        '/password-reset',
        '/forgot',
        '/recover',
        '/api/recover',
        '/change-password',
    ]

    TOKEN_PATTERNS = [
        r'token=([a-zA-Z0-9._-]+)',
        r'reset_token=([a-zA-Z0-9._-]+)',
        r'code=([a-zA-Z0-9._-]+)',
        r'resetCode=([a-zA-Z0-9._-]+)',
        r'key=([a-zA-Z0-9._-]+)',
        r'hash=([a-zA-Z0-9._-]+)',
        r'id=([a-zA-Z0-9._-]+)',
    ]

    WEAK_TOKEN_PATTERNS = [
        r'^\d{4,8}$',
        r'^\d{6}$',
        r'^[0-9a-f]{8}$',
        r'^[a-z]{6,12}$',
        r'^\d{4}-\d{4}-\d{4}-\d{4}$',
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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for endpoint in self.RESET_ENDPOINTS:
                    try:
                        body_text = await self._fetch_body(
                            target, port_to_check, ctx, host_header, endpoint
                        )
                        if body_text:
                            token_in_url = self._check_token_in_url(body_text, endpoint)
                            if token_in_url:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=(
                                        f'Insecure password reset: reset token appears in URL '
                                        f'on {endpoint}'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, token found in URL/link: {token_in_url[:80]}',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Insecure_Password_Reset',
                                        'https://portswigger.net/web-security/authentication/other-mechanisms',
                                    ]
                                ))
                                break

                            weak_token = self._check_weak_token(body_text)
                            if weak_token:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=(
                                        f'Insecure password reset: weak/predictable token pattern '
                                        f'on {endpoint}'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, weak token found: {weak_token[:60]}',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Insecure_Password_Reset',
                                        'https://portswigger.net/web-security/authentication/other-mechanisms',
                                    ]
                                ))
                                break

                            token_leak = self._check_token_leakage(body_text)
                            if token_leak:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=6.1,
                                    severity='medium',
                                    description=(
                                        f'Password reset token exposed in response body '
                                        f'on {endpoint}'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, token leaked in response: {token_leak[:60]}',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Insecure_Password_Reset',
                                        'https://portswigger.net/web-security/authentication/other-mechanisms',
                                    ]
                                ))
                                break

                            no_expiration = self._check_no_expiration(body_text)
                            if no_expiration:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=5.3,
                                    severity='medium',
                                    description=(
                                        f'Password reset may lack expiration: token validity period '
                                        f'not specified on {endpoint}'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, no expiration mentioned in response',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Insecure_Password_Reset',
                                        'https://portswigger.net/web-security/authentication/other-mechanisms',
                                    ]
                                ))
                                break
                    except Exception:
                        pass
                    if results:
                        break

                if not results:
                    for endpoint in ['/api/auth/reset', '/api/reset-password', '/api/forgot-password']:
                        try:
                            leak_finding = await self._check_api_token_leakage(
                                target, port_to_check, ctx, host_header, endpoint
                            )
                            if leak_finding:
                                results.append(leak_finding)
                                break
                        except Exception:
                            pass
                        if results:
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No password reset security issues detected on checked ports'
            ))

        return results

    def _check_token_in_url(self, body: str, endpoint: str) -> str | None:
        link_patterns = [
            r'https?://[^\s"\']+token=([^\s"\'&]+)',
            r'https?://[^\s"\']+reset_token=([^\s"\'&]+)',
            r'https?://[^\s"\']+code=([^\s"\'&]+)',
            r'https?://[^\s"\']+/reset/[^\s"\'/]+',
        ]
        for pattern in link_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(0)
        form_actions = re.findall(r'action=["\']([^"\']+)["\']', body, re.IGNORECASE)
        for action in form_actions:
            if 'token' in action.lower() or 'key' in action.lower() or 'code' in action.lower():
                return action
        return None

    def _check_weak_token(self, body: str) -> str | None:
        for pattern_str in self.TOKEN_PATTERNS:
            matches = re.findall(pattern_str, body, re.IGNORECASE)
            for token in matches:
                for weak_pattern in self.WEAK_TOKEN_PATTERNS:
                    if re.match(weak_pattern, token):
                        return token
                if len(token) < 16 and not re.match(r'^[a-f0-9]{32,}$', token, re.IGNORECASE):
                    if not re.match(r'^[A-Za-z0-9_-]{20,}$', token):
                        return token
        return None

    def _check_token_leakage(self, body: str) -> str | None:
        for pattern_str in self.TOKEN_PATTERNS:
            matches = re.findall(pattern_str, body, re.IGNORECASE)
            for token in matches:
                if len(token) >= 16:
                    context_pos = body.find(token)
                    start = max(0, context_pos - 50)
                    end = min(len(body), context_pos + len(token) + 50)
                    context = body[start:end]
                    suspicious = ['alert', 'console', 'log', 'innerhtml', 'debug']
                    for s in suspicious:
                        if s in context.lower():
                            return token
        return None

    def _check_no_expiration(self, body: str) -> bool:
        expiration_indicators = [
            'expir', 'valid for', 'time limit', 'minutes', 'hours',
            'temporary', 'one-time', 'single use', '24 hour',
        ]
        for indicator in expiration_indicators:
            if indicator in body.lower():
                return False
        return True

    async def _check_api_token_leakage(self, target: str, port: int, ctx,
                                       host_header: str, endpoint: str) -> PluginResult | None:
        body_text = await self._fetch_body(
            target, port, ctx, host_header, endpoint
        )
        if body_text:
            token_in_url = self._check_token_in_url(body_text, endpoint)
            if token_in_url:
                return PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='high',
                    description=f'Password reset token leaked via {endpoint}',
                    solution=self.SOLUTION,
                    evidence=f'Endpoint: {endpoint}, token leaked: {token_in_url[:100]}',
                    references=[
                        'https://owasp.org/www-community/attacks/Insecure_Password_Reset',
                        'https://portswigger.net/web-security/authentication/other-mechanisms',
                    ]
                )
        return None

    async def _fetch_body(self, target: str, port: int, ctx, host_header: str,
                          path: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'GET {path} HTTP/1.1\r\n'
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
                if len(response) > 32768:
                    break
            writer.close()
            await writer.wait_closed()
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None
