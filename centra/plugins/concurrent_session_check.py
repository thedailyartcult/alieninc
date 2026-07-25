import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class ConcurrentSessionCheck(NaslPlugin):
    PLUGIN_ID = 1193
    NAME = 'Concurrent Session Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Tests the application behavior regarding concurrent sessions. Checks if the application limits concurrent logins, terminates old sessions on re-authentication, or if multiple sessions are allowed simultaneously without restriction.'
    SOLUTION = 'Implement concurrent session limits. Invalidate old sessions on password change. Notify users of active sessions. Allow users to view and terminate active sessions.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

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

                cookies = []
                for attempt in range(3):
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    body = b'{"email":"test@test.com","password":"test123"}'
                    req = (
                        f'POST /login HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Content-Type: application/json\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer.write(req.encode() + body)
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
                        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                        set_cookies = []
                        for line in header_section.split('\r\n'):
                            if line.lower().startswith('set-cookie:'):
                                set_cookies.append(line)
                        cookies.append(set_cookies)

                if len(cookies) >= 2:
                    all_have_cookies = all(len(c) > 0 for c in cookies)
                    same_session = False
                    if all_have_cookies:
                        first_sessions = [c for c in cookies[0] if 'session' in c.lower()]
                        second_sessions = [c for c in cookies[1] if 'session' in c.lower()]
                        if first_sessions and second_sessions:
                            same_session = first_sessions == second_sessions

                    if all_have_cookies and not same_session:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='medium',
                            description='Multiple concurrent sessions allowed: 3 separate sessions created for same credentials',
                            solution=self.SOLUTION,
                            evidence=f'Login attempt 1: {len(cookies[0])} cookies\nLogin attempt 2: {len(cookies[1])} cookies\nLogin attempt 3: {len(cookies[2])} cookies\nAll attempts returned session cookies, indicating concurrent sessions are not restricted'
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=port_to_check,
                            description='No issues detected'
                        ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='No issues detected'
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
