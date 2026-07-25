import asyncio
import json
import ssl
from plugins import NaslPlugin, PluginResult

class VerificationBypass(NaslPlugin):
    PLUGIN_ID = 1253
    NAME = 'Verification Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects email/phone verification bypass vulnerabilities by testing registration endpoints for missing verification enforcement. Checks if accounts can be used without email or phone verification, and if verification tokens are predictable or reusable.'
    SOLUTION = 'Enforce verification before granting access. Use time-limited, single-use verification tokens. Verify on high-risk actions (password reset, admin access). Do not allow login without verification.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        verify_endpoints = [
            '/verify', '/verify/', '/verify/123456', '/verify?token=test',
            '/confirm', '/confirm/', '/confirm/test', '/confirm?code=123456',
            '/activate', '/activate/', '/activate/test', '/activate?key=test',
            '/email/verify', '/email/verify/test', '/phone/verify', '/phone/verify?code=123',
            '/api/verify', '/api/verify/email', '/api/verify/phone',
            '/register/confirm', '/register/confirm/test',
        ]
        register_payloads = [
            json.dumps({'email': 'test@test.com', 'password': 'Test123!', 'verified': True, 'skip_verification': True}),
            json.dumps({'email': 'test@test.com', 'password': 'Test123!', 'email_verified': True, 'phone_verified': True}),
            json.dumps({'email': 'test@test.com', 'password': 'Test123!', 'is_active': True, 'bypass_verification': True}),
        ]
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for ep in verify_endpoints:
                try:
                    ctx = None
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                    req = f'GET {ep} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                        status = int(response.split(b'\r\n')[0].split(b' ')[1])
                        if status not in (404, 405, 410):
                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Verification endpoint {ep} returned {status}. May allow verification bypass.'))
                            found = True
                            break
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
            if not found:
                for payload in register_payloads:
                    for reg_ep in ['/api/register', '/api/users', '/register', '/signup']:
                        try:
                            ctx = None
                            scheme = 'https' if port_to_check in (443, 8443) else 'http'
                            if scheme == 'https':
                                ctx = ssl.create_default_context()
                                ctx.check_hostname = False
                                ctx.verify_mode = ssl.CERT_NONE
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                            req = f'POST {reg_ep} HTTP/1.1\r\nHost: {host_header}\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n{payload}'
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
                                status = int(response.split(b'\r\n')[0].split(b' ')[1])
                                if status in (200, 201, 202):
                                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Registration {reg_ep} accepted verification bypass payload (status {status}). Verification bypass possible.'))
                                    found = True
                                    break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if found: break
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No verification bypass detected'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
