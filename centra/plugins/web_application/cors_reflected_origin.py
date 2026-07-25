"""
Plugin 1154: CORS Reflected Origin Detection
===============================================
Detects CORS configurations that reflect arbitrary Origin headers.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CorsReflectedOrigin(NaslPlugin):
    PLUGIN_ID = 1154
    NAME = 'CORS Reflected Origin Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects CORS configurations that reflect arbitrary Origin headers. '
        'Reflected origins allow any website to make authenticated cross-origin '
        'requests to the API by simply setting their Origin header. This can lead '
        'to data theft via CSRF-style attacks against authenticated users.'
    )
    SOLUTION = (
        'Use a whitelist of allowed origins. Never reflect the Origin header in '
        'Access-Control-Allow-Origin. Ensure Access-Control-Allow-Credentials is '
        'not set when using wildcard or reflected origins.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TEST_PATHS = ['/', '/api/', '/api/v1/', '/api/v1/users', '/graphql']

    TEST_ORIGINS = [
        'https://attacker.com',
        'https://evil.com',
        'https://malicious.com',
        'http://attacker.com',
        'null',
        'https://attacker.com:443',
        'https://sub.attacker.com',
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

                findings = []

                for path in self.TEST_PATHS:
                    for origin in self.TEST_ORIGINS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )

                            req = (
                                f'GET {path} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'User-Agent: Centra/1.0\r\n'
                                f'Origin: {origin}\r\n'
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

                            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                            headers = {}
                            for line in header_section.split('\r\n')[1:]:
                                if ':' in line:
                                    k, v = line.split(':', 1)
                                    headers[k.strip().lower()] = v.strip()

                            acao = headers.get('access-control-allow-origin', '')
                            acac = headers.get('access-control-allow-credentials', '')

                            if not acao:
                                continue

                            reflected = acao == origin or acao == origin.rstrip('/')
                            null_trusted = acao == 'null'
                            wildcard_with_creds = acao == '*' and acac.lower() == 'true'

                            if reflected or null_trusted or wildcard_with_creds:
                                issue_parts = [f'Path: {path}', f'Origin: {origin}', f'ACAO: {acao}']
                                if reflected:
                                    issue_parts.append('ORIGIN REFLECTED')
                                if null_trusted:
                                    issue_parts.append('NULL ORIGIN TRUSTED')
                                if wildcard_with_creds:
                                    issue_parts.append('WILDCARD WITH CREDENTIALS')
                                if acac.lower() == 'true':
                                    issue_parts.append('Credentials: true')

                                finding = ' | '.join(issue_parts)
                                if finding not in findings:
                                    findings.append(finding)

                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                            pass

                if findings:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='critical',
                        description=f'Reflected CORS origin detected: {len(findings)} vulnerable configuration(s)',
                        solution=self.SOLUTION,
                        evidence='; '.join(findings[:10]),
                        references=[
                            'https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny',
                            'https://www.tenable.com/plugins/nessus/10656',
                            'https://portswigger.net/web-security/cors',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='No reflected CORS origin detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description=f'Port {port_to_check} not reachable'
                ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ports reachable for CORS check'
            ))

        return results
