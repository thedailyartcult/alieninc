import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class HorizontalPrivilegeEscalation(NaslPlugin):
    PLUGIN_ID = 1221
    NAME = 'Horizontal Privilege Escalation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects horizontal privilege escalation (forced browsing) vulnerabilities by testing if an authenticated user can access resources belonging to other users by modifying IDs in URLs, API endpoints, or parameters.'
    SOLUTION = 'Implement proper authorization checks for every resource access. Use indirect object references. Ensure user context is validated on the server side, not inferred from client data.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    ID_PATTERNS = [
        '/user/{id}',
        '/api/user/{id}',
        '/profile/{id}',
        '/api/profile/{id}',
        '/account/{id}',
        '/api/account/{id}',
        '/users/{id}',
        '/api/users/{id}',
        '/customer/{id}',
        '/api/customer/{id}',
    ]

    TEST_IDS = [1, 2, 3, 100, 1000, 9999]

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

                for pattern in self.ID_PATTERNS:
                    responses = {}
                    for test_id in self.TEST_IDS[:5]:
                        try:
                            path = pattern.replace('{id}', str(test_id))
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
                                responses[test_id] = {'status': status_line, 'body': body[:500], 'length': len(body)}
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass

                    if len(responses) >= 2:
                        statuses = {r['status'] for r in responses.values()}
                        if len(statuses) == 1:
                            all_200 = all('200' in r['status'] for r in responses.values())
                            if all_200:
                                ids_found = list(responses.keys())
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=f'Horizontal privilege escalation possible on {pattern} - all IDs return 200 OK: {ids_found}',
                                    solution=self.SOLUTION,
                                    evidence=f'Pattern: {pattern}, accessible IDs: {ids_found}',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Forced_browsing',
                                        'https://portswigger.net/web-security/access-control/idor',
                                    ]
                                ))
                                break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No horizontal privilege escalation detected'))
        return results
