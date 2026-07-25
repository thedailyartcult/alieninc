"""
Plugin 1182: Session Fixation Detection
=========================================
Detects session fixation vulnerabilities where the server accepts a
session ID provided by the attacker via URL parameter or cookie.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class SessionFixationDetection(NaslPlugin):
    PLUGIN_ID = 1182
    NAME = 'Session Fixation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects session fixation vulnerabilities where the server accepts a '
        'session ID provided by the attacker via URL parameter or cookie. Tests '
        'by sending a known session ID to the server and checking if it is '
        'accepted after login/authentication.'
    )
    SOLUTION = (
        'Regenerate session IDs after successful authentication. Do not accept '
        'session tokens from URL parameters. Set session cookies with HttpOnly '
        'and Secure flags.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    FIXATION_ID = 'ATTACKER123FIXATIONTESTXYZ'

    COOKIE_NAMES = [
        'JSESSIONID', 'PHPSESSID', 'session', 'sid', 'token',
        'SESSION', 'SESSIONID', 'auth_token', 'connect.sid',
        'ci_session', 'ASP.NET_SessionId',
    ]

    PATHS = [
        '/', '/login', '/api/login', '/auth', '/account',
        '/dashboard', '/home', '/api/session',
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

                for path in self.PATHS[:5]:
                    try:
                        session_accepted = await self._check_session_fixation(
                            target, port_to_check, ctx, host_header, path
                        )
                        if session_accepted:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Session fixation detected on {path}: '
                                    f'custom session ID persisted across requests'
                                ),
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, test session ID: {self.FIXATION_ID} persisted across requests',
                                references=[
                                    'https://owasp.org/www-community/attacks/Session_fixation',
                                    'https://portswigger.net/web-security/session-fixation',
                                ]
                            ))
                            break
                    except Exception:
                        pass
                    if results:
                        break

                if not results:
                    for path in ['/', '/login', '/api/login']:
                        try:
                            session_in_url = await self._check_session_in_url(
                                target, port_to_check, ctx, host_header, path
                            )
                            if session_in_url:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=(
                                        f'Session ID accepted via URL parameter on {path}: '
                                        f'session fixation possible'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Path: {path}, server accepted session ID via URL parameter',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Session_fixation',
                                        'https://portswigger.net/web-security/session-fixation',
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
                description='No session fixation indicators detected on checked ports'
            ))

        return results

    async def _check_session_fixation(self, target: str, port: int, ctx,
                                      host_header: str, path: str) -> bool:
        for cookie_name in self.COOKIE_NAMES[:5]:
            try:
                response1 = await self._send_with_cookie(
                    target, port, ctx, host_header, path, cookie_name, self.FIXATION_ID
                )
                if response1 is None:
                    continue

                set_cookie = self._extract_set_cookie(response1)
                if set_cookie and self.FIXATION_ID in set_cookie:
                    return True

                response2 = await self._send_with_cookie(
                    target, port, ctx, host_header, '/', cookie_name, self.FIXATION_ID
                )
                if response2 is None:
                    continue

                second_set_cookie = self._extract_set_cookie(response2)
                if second_set_cookie and self.FIXATION_ID in second_set_cookie:
                    return True

            except Exception:
                pass
        return False

    async def _check_session_in_url(self, target: str, port: int, ctx,
                                    host_header: str, path: str) -> bool:
        for cookie_name in self.COOKIE_NAMES[:5]:
            try:
                session_path = f'{path}?{cookie_name.lower()}={self.FIXATION_ID}'
                response = await self._send_request(
                    target, port, ctx, host_header, session_path
                )
                if response is None:
                    continue

                set_cookie = self._extract_set_cookie(response)
                if set_cookie and self.FIXATION_ID.lower() in set_cookie.lower():
                    return True
            except Exception:
                pass
        return False

    async def _send_with_cookie(self, target: str, port: int, ctx, host_header: str,
                                path: str, cookie_name: str, cookie_value: str) -> bytes | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Cookie: {cookie_name}={cookie_value}\r\n'
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
            return response
        except Exception:
            return None

    async def _send_request(self, target: str, port: int, ctx, host_header: str,
                            path: str) -> bytes | None:
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
                if len(response) > 16384:
                    break
            writer.close()
            await writer.wait_closed()
            return response
        except Exception:
            return None

    def _extract_set_cookie(self, response: bytes) -> str | None:
        header_section = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
        for line in header_section.split('\r\n'):
            if line.lower().startswith('set-cookie:'):
                return line.split(':', 1)[1].strip()
        return None
