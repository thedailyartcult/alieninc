import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class OauthRedirectUriBypass(NaslPlugin):
    PLUGIN_ID = 1205
    NAME = 'OAuth Redirect URI Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects OAuth redirect URI validation bypass vulnerabilities by testing redirect_uri parameter manipulation. Tests for open redirect via directory traversal (redirect_uri=https://evil.com), subdomain matching flaws, and path validation bypass in OAuth flows.'
    SOLUTION = 'Use exact redirect URI matching. Validate against a whitelist of registered URIs. Do not allow open redirect. Reject URIs with unexpected host components.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    OAUTH_PATHS = ['/oauth/callback', '/auth/callback', '/api/auth/authorize', '/oauth/authorize', '/auth/authorize', '/api/oauth/callback']

    REDIRECT_URI_PAYLOADS = [
        {'name': 'external_domain', 'uri': 'https://evil.com/callback'},
        {'name': 'open_redirect', 'uri': 'https://evil.com'},
        {'name': 'subdomain_bypass', 'uri': 'https://evil.target.com/callback'},
        {'name': 'path_traversal', 'uri': 'https://target.com.evil.com/callback'},
        {'name': 'path_manipulation', 'uri': 'https://target.com/evil/callback'},
        {'name': 'double_slash', 'uri': 'https://target.com//evil.com/callback'},
        {'name': 'encoded_domain', 'uri': 'https://target.com%40evil.com/callback'},
        {'name': 'fragment_bypass', 'uri': 'https://evil.com#@target.com/callback'},
        {'name': 'dot_bypass', 'uri': 'https://evil.com/.target.com/callback'},
        {'name': 'port_bypass', 'uri': 'https://evil.com:443@target.com/callback'},
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

                for path in self.OAUTH_PATHS:
                    for payload in self.REDIRECT_URI_PAYLOADS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            qs = f'redirect_uri={payload["uri"]}&response_type=code&client_id=test'
                            req = f'GET {path}?{qs} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                                header_section = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else b''
                                status_line = header_section.split(b'\r\n')[0].decode('utf-8', errors='ignore') if header_section else ''
                                status_code = 0
                                parts = status_line.split(' ')
                                if len(parts) >= 2:
                                    try:
                                        status_code = int(parts[1])
                                    except ValueError:
                                        pass

                                location = ''
                                for line in header_section.split(b'\r\n')[1:]:
                                    if b':' in line:
                                        k, v = line.split(b':', 1)
                                        if k.strip().lower() == b'location':
                                            location = v.strip().decode('utf-8', errors='ignore')

                                body = response.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in response else response
                                body_str = body.decode('utf-8', errors='ignore')

                                redirect_occurred = False
                                if location and 'evil.com' in location.lower():
                                    redirect_occurred = True
                                elif body_str and ('evil.com' in body_str.lower() or 'redirect_uri' in body_str.lower()):
                                    if 'evil.com' in body_str.lower():
                                        redirect_occurred = True

                                if redirect_occurred or status_code in (301, 302, 303, 307, 308):
                                    if 'evil.com' in location.lower() or 'evil.com' in body_str.lower():
                                        results.append(PluginResult(
                                            vulnerable=True, target=target, port=port_to_check,
                                            cvss_score=self.CVSS_SCORE, severity='high',
                                            description=f'OAuth redirect URI bypass detected on {path} using {payload["name"]}',
                                            solution=self.SOLUTION,
                                            evidence=f'Path: {path}, technique: {payload["name"]}, redirect_uri: {payload["uri"]}',
                                            references=['https://owasp.org/www-community/attacks/Redirect_URI_Bypass']
                                        ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No OAuth redirect URI bypass vulnerabilities detected'))
        return results
