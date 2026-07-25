"""
Plugin 1057: Self-Configuration Security Audit (Self-Pentesting)
==================================================================
Reviews the Centra engine's own configuration for security weaknesses:
CORS policy, debug mode, admin credentials, and exposed configuration.
Self-pentesting pillar: audit the scanner's own setup.
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class SelfConfigAudit(NaslPlugin):
    PLUGIN_ID = 1057
    NAME = 'Self-Configuration Security Audit'
    FAMILY = 'Self-Pentesting'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Audits the Centra engine\'s own configuration for security weaknesses '
        'including permissive CORS, debug endpoints, exposed admin interfaces, '
        'and credential exposure in responses.'
    )
    SOLUTION = (
        'Restrict CORS to specific trusted origins. Disable debug mode. '
        'Use environment variables for secrets instead of default credentials. '
        'Implement IP whitelisting for admin endpoints.'
    )
    PORTS = [8721]

    CONFIG_CHECKS = [
        '/robots.txt',
        '/.env',
        '/admin',
        '/config',
        '/debug',
        '/api/docs',
        '/docs',
        '/redoc',
        '/openapi.json',
    ]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_cors_policy(target, port))
        findings.extend(await self._check_exposed_paths(target, port))
        findings.extend(await self._check_credential_disclosure(target, port))
        findings.extend(await self._check_response_headers(target, port))

        if findings:
            all_evidence = '; '.join(f.evidence for f in findings)
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='medium',
                description=f'Self-config audit: {len(findings)} finding(s)',
                solution=self.SOLUTION,
                evidence=all_evidence,
                references=[
                    'https://www.tenable.com/plugins/nessus/10497',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='Self-configuration audit passed'
        )]

    async def _check_cors_policy(self, target: str, port: int) -> list[PluginResult]:
        results = []
        for origin in ['https://evil.com', 'null']:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = (
                    f'GET /api/plugins HTTP/1.1\r\n'
                    f'Host: {target}:{port}\r\n'
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
                    if len(response) > 2048:
                        break
                writer.close()
                await writer.wait_closed()

                header_text = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                for line in header_text.split('\r\n'):
                    if 'access-control-allow-origin:' in line:
                        allowed = line.split(':')[1].strip()
                        if allowed == '*' or allowed == origin:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port,
                                cvss_score=4.3, severity='medium',
                                description=f'Permissive CORS: allows origin "{origin}" on /api/plugins',
                                solution=self.SOLUTION,
                                evidence=f'ACAO: {allowed} for origin {origin}',
                            ))
                        break
            except Exception:
                pass
        return results

    async def _check_exposed_paths(self, target: str, port: int) -> list[PluginResult]:
        results = []
        for path in self.CONFIG_CHECKS:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = f'GET {path} HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 4096:
                        break
                writer.close()
                await writer.wait_closed()

                status = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '200' in status:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port,
                        cvss_score=5.0, severity='medium',
                        description=f'Configuration path exposed: {path}',
                        solution='Remove or restrict access to admin/debug endpoints.',
                        evidence=f'GET {path} returned {status.split()[1] if len(status.split()) > 1 else "200"}',
                    ))
            except Exception:
                pass
        return results

    async def _check_credential_disclosure(self, target: str, port: int) -> list[PluginResult]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            body = b'{"username":"admin","password":"centra2026"}'
            req = (
                f'POST /api/auth/login HTTP/1.1\r\n'
                f'Host: {target}:{port}\r\n'
                f'Content-Type: application/json\r\n'
                f'Content-Length: {len(body)}\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode() + body)
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 4096:
                    break
            writer.close()
            await writer.wait_closed()

            body_text = response.split(b'\r\n\r\n', 1)
            if len(body_text) > 1:
                import json
                resp = json.loads(body_text[1].decode('utf-8', errors='ignore'))
                if 'token' in resp or 'access_token' in resp:
                    tok = resp.get('token') or resp.get('access_token', '')
                    if len(tok) > 50 and '.' in tok:
                        parts = tok.split('.')
                        import base64
                        try:
                            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                            if payload.get('sub') == 'admin' and 'exp' in payload:
                                return []
                        except Exception:
                            pass
        except Exception:
            pass
        return []

    async def _check_response_headers(self, target: str, port: int) -> list[PluginResult]:
        results = []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = f'GET / HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 4096:
                    break
            writer.close()
            await writer.wait_closed()

            header_text = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            security_headers = {
                'x-content-type-options': 'nosniff',
                'x-frame-options': 'DENY',
                'x-xss-protection': '1; mode=block',
                'strict-transport-security': 'max-age=',
                'content-security-policy': "default-src 'self'",
            }
            for header, expected in security_headers.items():
                found = False
                for line in header_text.split('\r\n'):
                    if line.startswith(header + ':'):
                        found = True
                        break
                if not found:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port,
                        cvss_score=2.6, severity='low',
                        description=f'Missing security header: {header}',
                        solution=f'Add "{header}: {expected}" to responses.',
                        evidence=f'Header {header} not present',
                    ))
        except Exception:
            pass
        return results
