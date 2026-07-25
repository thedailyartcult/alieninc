"""
Plugin 1122: Insecure Direct Object Reference (IDOR) Detection
================================================================
Detects IDOR vulnerabilities by probing common sequential/guessable
IDs in URL patterns (/user/1, /api/users/1, /invoice/1001).
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class IdorDetection(NaslPlugin):
    PLUGIN_ID = 1122
    NAME = 'Insecure Direct Object Reference (IDOR) Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects Insecure Direct Object Reference (IDOR) vulnerabilities by '
        'probing common sequential/guessable IDs in URL patterns '
        '(/user/1, /api/users/1, /invoice/1001). IDOR occurs when an application '
        'exposes direct references to internal objects without proper '
        'authorization checks.'
    )
    SOLUTION = (
        'Use indirect object references (non-guessable IDs). Implement proper '
        'authorization checks for every object access. Use UUIDs instead of '
        'sequential integers.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    IDOR_PATTERNS = [
        '/user/1', '/api/user/1', '/api/users/1', '/profile/1',
        '/account/1', '/customer/1', '/invoice/1001', '/order/1001',
        '/api/v1/user/1', '/admin/user/1', '/document/1', '/file/1',
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

                for pattern in self.IDOR_PATTERNS:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    req = (
                        f'GET {pattern} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
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
                            if len(response) > 16384:
                                break
                    except asyncio.TimeoutError:
                        pass

                    writer.close()
                    await writer.wait_closed()

                    header_section = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
                    body_section = response.split(b'\r\n\r\n', 1)
                    body_text = body_section[1].decode('utf-8', errors='ignore') if len(body_section) > 1 else ''

                    status_code = 0
                    for line in header_section.split('\r\n'):
                        if line.startswith('HTTP/'):
                            try:
                                status_code = int(line.split(' ')[1])
                            except (IndexError, ValueError):
                                pass
                            break

                    if status_code in (200, 201) and len(body_text) > 100:
                        json_indicators = ['"id"', '"name"', '"email"', '"role"', '"data"']
                        if any(ind in body_text for ind in json_indicators):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=f'Potential IDOR at {pattern} (returned data for sequential ID)',
                                solution=self.SOLUTION,
                                evidence=f'Pattern: {pattern}, HTTP {status_code}, response body contains object data',
                                references=[
                                    'https://owasp.org/www-community/attacks/Insecure_Direct_Object_Reference_(IDOR)',
                                    'https://portswigger.net/web-security/access-control/idor',
                                ]
                            ))
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No IDOR indicators detected on checked ports'
            ))

        return results
