"""
Plugin 1134: CORS Misconfiguration Deep Evaluation
=====================================================
Deep evaluation of CORS configuration for various misconfigurations.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CorsEvaluation(NaslPlugin):
    PLUGIN_ID = 1134
    NAME = 'CORS Misconfiguration Deep Evaluation'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Deep evaluation of CORS (Cross-Origin Resource Sharing) configuration. '
        'Beyond checking for wildcard origins, this plugin tests for Trusted '
        'null origin, dynamic origin reflection, exposed credentials with '
        'wildcard, and permissive allowed methods/headers. CORS misconfigurations '
        'enable cross-origin data theft.'
    )
    SOLUTION = (
        'Use specific origins instead of wildcards or reflection. Only include '
        'Access-Control-Allow-Credentials: true when origin is explicitly '
        'whitelisted. Restrict allowed methods and headers.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TEST_ORIGINS = [
        ('null', 'Null origin'),
        ('https://attacker.com', 'Reflected origin'),
        ('https://attacker.com.evil.com', 'Subdomain bypass'),
        ('https://attacker.com:443', 'Port variation'),
        ('http://attacker.com', 'Scheme downgrade'),
        ('https://evil.com', 'Arbitrary domain'),
        ('https://malicious.com', 'Arbitrary domain 2'),
    ]

    TEST_PATHS = ['/', '/api/', '/api/v1/', '/api/v1/users']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ports = self.PORTS if port is None else [port]

        for p in ports:
            try:
                scheme = 'https' if p in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                findings = []

                for path in self.TEST_PATHS:
                    for origin, origin_label in self.TEST_ORIGINS:
                        headers = await self._fetch_with_origin(target, p, path, origin, ctx)
                        if headers is None:
                            continue

                        acao = headers.get('access-control-allow-origin', '')
                        acac = headers.get('access-control-allow-credentials', '')
                        acam = headers.get('access-control-allow-methods', '')
                        acah = headers.get('access-control-allow-headers', '')

                        if not acao:
                            continue

                        issues = []

                        if acao == '*':
                            issues.append('Wildcard origin (Allow-Origin: *)')
                            if acac.lower() == 'true':
                                issues.append('Credentials with wildcard origin (VULNERABLE)')

                        if acao == 'null':
                            issues.append('Null origin is trusted (VULNERABLE)')

                        if acao == origin or acao == origin.rstrip('/'):
                            if origin_label == 'Reflected origin' or origin_label == 'Arbitrary domain':
                                issues.append(f'Dynamic origin reflection: sent "{origin}", echoed "{acao}"')

                        if acac.lower() == 'true':
                            if acao == '*':
                                issues.append('Credentials: true with wildcard (INVALID PER SPEC)')
                            elif 'reflected' in origin_label.lower() or 'arbitrary' in origin_label.lower():
                                issues.append(f'Credentials: true with dynamically reflected origin')

                        if acam and acam.strip(' ,') == '*':
                            issues.append(f'Wildcard allowed methods: {acam}')

                        if acah and acah.strip(' ,') == '*':
                            issues.append(f'Wildcard allowed headers: {acah}')

                        if issues:
                            finding = f'{path} ({origin_label}): {" | ".join(issues)}'
                            if finding not in findings:
                                findings.append(finding)

                if findings:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'CORS misconfiguration(s): {len(findings)} issue(s) detected',
                        solution=self.SOLUTION,
                        evidence='; '.join(findings),
                        references=[
                            'https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny',
                            'https://www.tenable.com/plugins/nessus/10656',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No CORS misconfigurations detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _fetch_with_origin(self, target: str, port: int, path: str,
                                  origin: str, ctx: ssl.SSLContext | None) -> dict[str, str] | None:
        try:
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
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

            header_section = response.split(b'\r\n\r\n')[0].decode(errors='ignore')
            headers = {}
            for line in header_section.split('\r\n')[1:]:
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip().lower()] = v.strip()

            return headers

        except Exception:
            return None
