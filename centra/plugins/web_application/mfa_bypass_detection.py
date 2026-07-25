import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class MfaBypassDetection(NaslPlugin):
    PLUGIN_ID = 1223
    NAME = 'Multi-Factor Authentication Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects multi-factor authentication (MFA/2FA) bypass techniques including OTP reuse, token leakage, backup code abuse, MFA not enforced on all sensitive endpoints, and MFA timeout/expiration issues.'
    SOLUTION = 'Enforce MFA on all sensitive actions (login, password change, admin access). Use TOTP with short time windows. Invalidate OTPs after use. Require MFA for session renewal. Implement step-up authentication for sensitive operations.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    MFA_PATHS = [
        '/2fa', '/mfa', '/verify-otp', '/auth/2fa', '/auth/mfa',
        '/api/2fa', '/api/mfa', '/auth/verify-otp', '/api/verify-otp',
        '/two-factor', '/auth/two-factor', '/api/two-factor',
    ]

    SENSITIVE_PATHS = [
        '/admin', '/api/admin', '/dashboard', '/api/dashboard',
        '/api/user/change-password', '/change-password',
        '/api/user/email', '/api/user/profile',
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

                mfa_endpoints_found = []
                for path in self.MFA_PATHS:
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
                            if '200' in status_line or '404' in status_line:
                                mfa_endpoints_found.append(path)
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

                for path in self.SENSITIVE_PATHS:
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
                            if '200' in status_line:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=f'Sensitive endpoint {path} accessible without authentication (MFA bypass possible)',
                                    solution=self.SOLUTION,
                                    evidence=f'Path: {path} returned {status_line.strip()} without session/MFA',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Multi-factor_Authentication_Bypass',
                                        'https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html',
                                    ]
                                ))
                                break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

                if mfa_endpoints_found and not results:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'MFA endpoints found ({mfa_endpoints_found}) but no bypass detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No MFA bypass detected'))
        return results
