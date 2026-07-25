"""
Plugin 1037: CORS Wildcard Origin Detection
==============================================
Detects overly permissive CORS policies (Access-Control-Allow-Origin: *).
Real CVEs: CVE-2024-25124 (CORS wildcard), CVE-2026-54290 (CORS misconfig)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class CorsWildcard(NaslPlugin):
    PLUGIN_ID = 1037
    NAME = 'CORS Wildcard Origin Detection'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 4.3
    DESCRIPTION = (
        'The web server allows cross-origin requests from any domain via '
        'Access-Control-Allow-Origin: * (with or without credentials). '
        'This enables data theft via cross-origin requests from malicious sites.'
    )
    SOLUTION = (
        'Restrict CORS to specific trusted origins only. Avoid using wildcard '
        'origin with credentials. Use a whitelist approach for allowed origins.'
    )
    CVE = ['CVE-2024-25124', 'CVE-2026-54290']
    PORTS = [80, 443]

    TEST_ORIGINS = [
        'https://evil.com',
        'http://attacker.io',
        'https://malicious.example',
        'null',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        results = []

        for origin in self.TEST_ORIGINS:
            try:
                result = await self._check_origin(target, port, origin)
                if result:
                    results.append(result)
            except Exception:
                pass

        if results:
            wildcard_with_creds = any(
                'wildcard' in r.evidence and 'Allow-Credentials: true' in r.evidence
                for r in results
            )
            sev = 'high' if wildcard_with_creds else 'medium'
            cvss = 6.1 if wildcard_with_creds else 4.3

            origins_found = ', '.join(r.evidence.split('origin:')[1].split(',')[0].strip() if 'origin:' in r.evidence else '?' for r in results)
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=sev,
                description=f'Overly permissive CORS policy: {len(results)} origins allowed',
                solution=self.SOLUTION,
                evidence=f'Allowed origins: {origins_found}. "Access-Control-Allow-Credentials: true" with wildcard: {wildcard_with_creds}',
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                    'https://www.tenable.com/plugins/nessus/134662',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='CORS policy appears properly restricted'
        )]

    async def _check_origin(self, target: str, port: int, origin: str) -> PluginResult | None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target, port), timeout=5
        )

        req = (
            f'GET / HTTP/1.1\r\n'
            f'Host: {target}\r\n'
            f'Origin: {origin}\r\n'
            f'User-Agent: Centra/1.0\r\n'
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
            if len(response) > 8192:
                break

        writer.close()
        await writer.wait_closed()

        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
        headers = {}
        for line in header_section.split('\r\n')[1:]:
            if ':' in line:
                key, val = line.split(':', 1)
                headers[key.strip().lower()] = val.strip()

        acao = headers.get('access-control-allow-origin', '')
        acac = headers.get('access-control-allow-credentials', '')

        if acao == '*' or acao == origin:
            details = f'origin: {origin}'
            if acao == '*':
                details += ', wildcard: true'
            if acac.lower() == 'true':
                details += ', Allow-Credentials: true'
            return PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=4.3,
                severity='medium',
                description=f'CORS allows origin: {origin}',
                solution=self.SOLUTION,
                evidence=details,
            )

        return None
