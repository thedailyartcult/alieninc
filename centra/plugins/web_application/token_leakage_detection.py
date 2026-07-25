"""
Plugin 1185: Authentication Token Leakage Detection
=====================================================
Detects leakage of authentication tokens (JWT, session IDs, API keys)
in URLs, Referer headers, and cached responses.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class TokenLeakageDetection(NaslPlugin):
    PLUGIN_ID = 1185
    NAME = 'Authentication Token Leakage Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects leakage of authentication tokens (JWT, session IDs, API keys) '
        'in URLs, Referer headers, and cached responses. Tokens exposed in URLs '
        'can be logged by proxies or leaked via Referer headers to third-party sites.'
    )
    SOLUTION = (
        'Transmit tokens only via securely flagged cookies or Authorization '
        'headers. Never include tokens in URLs. Use Referrer-Policy to control '
        'referrer leakage. Disable caching for authenticated responses.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TOKEN_PATTERNS = [
        (r'access_token=([^&\s"\']+)', 'access_token'),
        (r'id_token=([^&\s"\']+)', 'id_token'),
        (r'refresh_token=([^&\s"\']+)', 'refresh_token'),
        (r'token=([^&\s"\']+)', 'token'),
        (r'api_key=([^&\s"\']+)', 'api_key'),
        (r'apikey=([^&\s"\']+)', 'apikey'),
        (r'secret=([^&\s"\']+)', 'secret'),
        (r'jwt=([^&\s"\']+)', 'jwt'),
        (r'bearer=([^&\s"\']+)', 'bearer'),
        (r'auth=([^&\s"\']+)', 'auth'),
        (r'session=([^&\s"\']+)', 'session'),
        (r'sid=([^&\s"\']+)', 'sid'),
        (r'password=([^&\s"\']+)', 'password'),
    ]

    JWT_PATTERN = re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+')

    CACHE_CONTROL_DANGEROUS = [
        b'cache-control:.*no-cache',
        b'cache-control:.*no-store',
        b'cache-control:.*must-revalidate',
        b'pragma:.*no-cache',
    ]

    PATHS = [
        '/', '/api', '/api/user', '/api/profile', '/dashboard',
        '/account', '/settings', '/api/settings', '/login',
    ]

    EXTERNAL_LINKS_PATTERN = re.compile(
        r'https?://(?!([a-zA-Z0-9.-]*\.)?(alieninc\.tech|example\.com|localhost|127\.0\.0\.1))'
        r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s"\'<>]*'
    )

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

                for path in self.PATHS:
                    try:
                        response = await self._fetch_response(
                            target, port_to_check, ctx, host_header, path
                        )
                        if response is None:
                            continue

                        headers, body = self._split_response(response)

                        tokens_in_url = self._check_tokens_in_urls(body, path)
                        if tokens_in_url:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Authentication token leaked in URL on {path}: '
                                    f'{tokens_in_url[0]} parameter exposed'
                                ),
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, token type leaked: {tokens_in_url[0]}, value: {tokens_in_url[1][:40]}',
                                references=[
                                    'https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url',
                                    'https://portswigger.net/web-security/information-disclosure',
                                ]
                            ))
                            break

                        jwt_leak = self._check_jwt_in_body(body, path)
                        if jwt_leak:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=f'JWT token leaked in response body on {path}',
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, JWT token found in response body',
                                references=[
                                    'https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url',
                                    'https://portswigger.net/web-security/jwt',
                                ]
                            ))
                            break

                        referrer_leak = self._check_referrer_leakage(response, path)
                        if referrer_leak:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=6.1,
                                severity='medium',
                                description=(
                                    f'Referer header may leak token on {path}: '
                                    f'no Referrer-Policy or insecure Referrer-Policy'
                                ),
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, {referrer_leak}',
                                references=[
                                    'https://developer.mozilla.org/en-US/docs/Web/Security/Referer_header:_privacy_and_security_concerns',
                                    'https://portswigger.net/web-security/information-disclosure',
                                ]
                            ))
                            break

                        cache_leak = self._check_cache_leakage(response, path)
                        if cache_leak:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=5.3,
                                severity='medium',
                                description=f'Authenticated response may be cached on {path}',
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, {cache_leak}',
                                references=[
                                    'https://owasp.org/www-community/vulnerabilities/Information_exposure_through_caching',
                                    'https://portswigger.net/web-security/information-disclosure',
                                ]
                            ))
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
                description='No authentication token leakage detected on checked ports'
            ))

        return results

    def _check_tokens_in_urls(self, body: str, path: str) -> tuple[str, str] | None:
        for pattern, token_type in self.TOKEN_PATTERNS:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for match in matches:
                if len(match) > 3:
                    return (token_type, match)
        return None

    def _check_jwt_in_body(self, body: str, path: str) -> bool:
        return bool(self.JWT_PATTERN.search(body))

    def _check_referrer_leakage(self, response: bytes, path: str) -> str | None:
        headers = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
        header_lower = headers.lower()

        if 'referrer-policy' in header_lower:
            return None

        external_links = self._find_external_links(response)
        if external_links:
            return f'External links found without Referrer-Policy: {external_links[:2]}'

        return None

    def _check_cache_leakage(self, response: bytes, path: str) -> str | None:
        headers = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
        header_bytes = response.split(b'\r\n\r\n', 1)[0].lower()

        for pattern in self.CACHE_CONTROL_DANGEROUS:
            if re.search(pattern, header_bytes):
                return None

        if b'cache-control' not in header_bytes:
            return 'No Cache-Control header set'

        if b'cache-control:.*private' in header_bytes or b'cache-control:.*public' in header_bytes:
            return 'Cache-Control allows caching of authenticated response'

        return None

    def _find_external_links(self, response: bytes) -> list[str]:
        body = response.split(b'\r\n\r\n', 1)
        if len(body) < 2:
            return []
        body_text = body[1].decode('utf-8', errors='ignore')
        matches = self.EXTERNAL_LINKS_PATTERN.findall(body_text)
        return list(set(matches))[:5]

    async def _fetch_response(self, target: str, port: int, ctx,
                              host_header: str, path: str) -> bytes | None:
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
                if len(response) > 65536:
                    break
            writer.close()
            await writer.wait_closed()
            return response if response else None
        except Exception:
            return None

    def _split_response(self, response: bytes) -> tuple[str, str]:
        if not response:
            return '', ''
        parts = response.split(b'\r\n\r\n', 1)
        headers = parts[0].decode('utf-8', errors='ignore') if parts else ''
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        return headers, body
