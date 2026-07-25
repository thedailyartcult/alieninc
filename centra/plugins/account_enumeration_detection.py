"""
Plugin 1183: Account Enumeration Detection
============================================
Detects account enumeration vulnerabilities by analyzing differences
in responses for valid vs invalid usernames during login or
password reset.
"""
import asyncio
import ssl
import time
import urllib.parse

from plugins import NaslPlugin, PluginResult


class AccountEnumerationDetection(NaslPlugin):
    PLUGIN_ID = 1183
    NAME = 'Account Enumeration Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects account enumeration vulnerabilities by analyzing differences '
        'in responses for valid vs invalid usernames during login or password '
        'reset. Differences in error messages, response times, or status codes '
        'can reveal valid user accounts.'
    )
    SOLUTION = (
        'Use generic error messages for all authentication failures. Ensure '
        'consistent response times. Return the same HTTP status code regardless '
        'of username validity.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    LIKELY_VALID_USERNAMES = [
        'admin', 'administrator', 'root', 'user', 'test',
        'info', 'support', 'contact', 'webmaster', 'nobody',
    ]

    LIKELY_INVALID_USERNAMES = [
        'nonexistent_user_abc123xyz', 'invalid_user_999999',
        'zzz_nonexistent', 'nobody_should_exist_42',
    ]

    LOGIN_PATHS = [
        '/login', '/api/login', '/auth', '/api/auth',
        '/signin', '/api/signin', '/account/login',
    ]

    FORGOT_PASSWORD_PATHS = [
        '/forgot-password', '/api/forgot-password', '/reset-password',
        '/api/reset-password', '/password-reset', '/forgot',
    ]

    ERROR_INDICATORS = [
        'invalid username', 'user not found', 'account not found',
        'invalid user', 'no account', 'does not exist',
        'not registered', 'unknown user', 'invalid login',
        'incorrect password', 'wrong password',
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

                for path in self.LOGIN_PATHS:
                    try:
                        login_findings = await self._check_login_endpoint(
                            target, port_to_check, ctx, host_header, path
                        )
                        if login_findings:
                            results.extend(login_findings)
                            break
                    except Exception:
                        pass
                    if results:
                        break

                if not results:
                    for path in self.FORGOT_PASSWORD_PATHS:
                        try:
                            pw_findings = await self._check_forgot_password_endpoint(
                                target, port_to_check, ctx, host_header, path
                            )
                            if pw_findings:
                                results.extend(pw_findings)
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
                description='No account enumeration indicators detected on checked ports'
            ))

        return results

    async def _check_login_endpoint(self, target: str, port: int, ctx,
                                    host_header: str, path: str) -> list[PluginResult]:
        findings = []

        valid_responses = []
        for username in self.LIKELY_VALID_USERNAMES[:3]:
            try:
                resp, timing = await self._send_login_request(
                    target, port, ctx, host_header, path, username, 'wrongpassword123!'
                )
                if resp:
                    valid_responses.append((username, resp, timing))
            except Exception:
                pass

        invalid_responses = []
        for username in self.LIKELY_INVALID_USERNAMES[:3]:
            try:
                resp, timing = await self._send_login_request(
                    target, port, ctx, host_header, path, username, 'wrongpassword123!'
                )
                if resp:
                    invalid_responses.append((username, resp, timing))
            except Exception:
                pass

        if not valid_responses or not invalid_responses:
            return findings

        for v_username, v_resp, v_time in valid_responses:
            v_header, v_body = self._split_response(v_resp)
            v_status = self._extract_status(v_header)
            v_body_lower = v_body.lower()

            for i_username, i_resp, i_time in invalid_responses:
                i_header, i_body = self._split_response(i_resp)
                i_status = self._extract_status(i_header)
                i_body_lower = i_body.lower()

                if v_status != i_status:
                    findings.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description=(
                            f'Account enumeration detected on {path}: different HTTP status '
                            f'codes for valid vs invalid usernames'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'Valid "{v_username}": HTTP {v_status}, Invalid "{i_username}": HTTP {i_status}',
                        references=[
                            'https://owasp.org/www-community/attacks/Account_information_disclosure',
                            'https://portswigger.net/web-security/authentication/other-mechanisms',
                        ]
                    ))
                    return findings

                error_diff = self._compare_error_messages(v_body_lower, i_body_lower)
                if error_diff:
                    findings.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description=(
                            f'Account enumeration detected on {path}: different error messages '
                            f'for valid vs invalid usernames'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'Valid "{v_username}": "{error_diff[0]}", Invalid "{i_username}": "{error_diff[1]}"',
                        references=[
                            'https://owasp.org/www-community/attacks/Account_information_disclosure',
                            'https://portswigger.net/web-security/authentication/other-mechanisms',
                        ]
                    ))
                    return findings

                if v_time and i_time and abs(v_time - i_time) > 0.5:
                    findings.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='low',
                        description=(
                            f'Account enumeration possible on {path}: response time differs '
                            f'between valid and invalid usernames'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'Valid "{v_username}": {v_time:.2f}s, Invalid "{i_username}": {i_time:.2f}s',
                        references=[
                            'https://owasp.org/www-community/attacks/Account_information_disclosure',
                            'https://portswigger.net/web-security/authentication/other-mechanisms',
                        ]
                    ))
                    return findings

        return findings

    async def _check_forgot_password_endpoint(self, target: str, port: int, ctx,
                                              host_header: str, path: str) -> list[PluginResult]:
        findings = []

        valid_responses = []
        for username in self.LIKELY_VALID_USERNAMES[:3]:
            try:
                resp, timing = await self._send_forgot_request(
                    target, port, ctx, host_header, path, username
                )
                if resp:
                    valid_responses.append((username, resp, timing))
            except Exception:
                pass

        invalid_responses = []
        for username in self.LIKELY_INVALID_USERNAMES[:3]:
            try:
                resp, timing = await self._send_forgot_request(
                    target, port, ctx, host_header, path, username
                )
                if resp:
                    invalid_responses.append((username, resp, timing))
            except Exception:
                pass

        if not valid_responses or not invalid_responses:
            return findings

        for v_username, v_resp, v_time in valid_responses:
            v_header, v_body = self._split_response(v_resp)
            v_status = self._extract_status(v_header)
            v_body_lower = v_body.lower()

            for i_username, i_resp, i_time in invalid_responses:
                i_header, i_body = self._split_response(i_resp)
                i_status = self._extract_status(i_header)
                i_body_lower = i_body.lower()

                if v_status != i_status:
                    findings.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description=(
                            f'Account enumeration detected on password reset {path}: '
                            f'different HTTP status codes'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'Valid "{v_username}": HTTP {v_status}, Invalid "{i_username}": HTTP {i_status}',
                        references=[
                            'https://owasp.org/www-community/attacks/Account_information_disclosure',
                            'https://portswigger.net/web-security/authentication/other-mechanisms',
                        ]
                    ))
                    return findings

                error_diff = self._compare_error_messages(v_body_lower, i_body_lower)
                if error_diff:
                    findings.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description=f'Account enumeration detected on password reset {path}: different messages',
                        solution=self.SOLUTION,
                        evidence=f'Valid "{v_username}": "{error_diff[0]}", Invalid "{i_username}": "{error_diff[1]}"',
                        references=[
                            'https://owasp.org/www-community/attacks/Account_information_disclosure',
                            'https://portswigger.net/web-security/authentication/other-mechanisms',
                        ]
                    ))
                    return findings

        return findings

    def _compare_error_messages(self, valid_body: str, invalid_body: str) -> tuple[str, str] | None:
        valid_errors = []
        invalid_errors = []
        for indicator in self.ERROR_INDICATORS:
            if indicator in valid_body:
                valid_errors.append(indicator)
            if indicator in invalid_body:
                invalid_errors.append(indicator)
        if valid_errors and invalid_errors:
            if valid_errors != invalid_errors:
                return (', '.join(valid_errors), ', '.join(invalid_errors))
        elif valid_errors and not invalid_errors:
            return (valid_errors[0], 'no error message')
        elif not valid_errors and invalid_errors:
            return ('no error message', invalid_errors[0])
        return None

    async def _send_login_request(self, target: str, port: int, ctx, host_header: str,
                                  path: str, username: str, password: str) -> tuple[bytes | None, float | None]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            body_data = f'username={urllib.parse.quote(username)}&password={urllib.parse.quote(password)}'
            req = (
                f'POST {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Content-Type: application/x-www-form-urlencoded\r\n'
                f'Content-Length: {len(body_data)}\r\n'
                f'Connection: close\r\n\r\n{body_data}'
            )
            start = time.monotonic()
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
            end = time.monotonic()
            writer.close()
            await writer.wait_closed()
            return response, end - start
        except Exception:
            return None, None

    async def _send_forgot_request(self, target: str, port: int, ctx, host_header: str,
                                   path: str, username: str) -> tuple[bytes | None, float | None]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            body_data = f'email={urllib.parse.quote(username)}&username={urllib.parse.quote(username)}'
            req = (
                f'POST {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Content-Type: application/x-www-form-urlencoded\r\n'
                f'Content-Length: {len(body_data)}\r\n'
                f'Connection: close\r\n\r\n{body_data}'
            )
            start = time.monotonic()
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
            end = time.monotonic()
            writer.close()
            await writer.wait_closed()
            return response, end - start
        except Exception:
            return None, None

    def _split_response(self, response: bytes) -> tuple[str, str]:
        if not response:
            return '', ''
        parts = response.split(b'\r\n\r\n', 1)
        headers = parts[0].decode('utf-8', errors='ignore') if parts else ''
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        return headers, body

    def _extract_status(self, header_section: str) -> int | None:
        first_line = header_section.split('\r\n')[0] if header_section else ''
        if ' ' in first_line:
            parts = first_line.split(' ')
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    pass
        return None
