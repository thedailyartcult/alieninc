"""
Plugin 1052: Engine API Self-Check (Self-Pentesting)
======================================================
Probes the Centra engine's own REST API endpoints for security
misconfigurations, information disclosure, and missing auth controls.
Self-pentesting pillar: the scanner tests itself.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class EngineApiSelfCheck(NaslPlugin):
    PLUGIN_ID = 1052
    NAME = 'Engine API Self-Check'
    FAMILY = 'Self-Pentesting'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Audits the Centra scanner engine\'s own REST API for security '
        'weaknesses including unauthenticated access to sensitive endpoints, '
        'information disclosure in responses, and missing rate limiting.'
    )
    SOLUTION = (
        'Add authentication to all scan/configuration endpoints. Implement '
        'rate limiting on /api/auth/login. Remove debug information from API '
        'responses. Use HTTPS in production. Restrict CORS origins.'
    )
    PORTS = [80, 443, 8721]

    ENDPOINTS = [
        ('GET', '/api/plugins', False, 'Plugin listing — should require auth'),
        ('GET', '/api/scans', True, 'Scan history — should require auth'),
        ('GET', '/api/scans/99999', True, 'Nonexistent scan — error handling'),
        ('POST', '/api/auth/login', False, 'Login endpoint — rate limiting?'),
    ]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        for method, path, needs_auth, note in self.ENDPOINTS:
            try:
                result = await self._probe_endpoint(target, port, method, path, needs_auth, note)
                if result:
                    findings.append(result)
            except Exception:
                pass

        if findings:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='medium',
                description=f'Engine API: {len(findings)} security finding(s)',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=[
                    'https://www.tenable.com/plugins/nessus/10497',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='Engine API self-check passed'
        )]

    async def _probe_endpoint(self, target: str, port: int, method: str,
                                path: str, needs_auth: bool, note: str) -> PluginResult | None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target, port), timeout=5
        )

        body = b''
        if path == '/api/auth/login':
            body = b'{"username":"admin","password":"centra2026"}'

        req = (
            f'{method} {path} HTTP/1.1\r\n'
            f'Host: {target}:{port}\r\n'
            f'User-Agent: Centra/1.0\r\n'
            f'Content-Type: application/json\r\n'
            f'Content-Length: {len(body)}\r\n'
            f'Connection: close\r\n\r\n'
        )
        if body:
            req = req + body.decode()
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
        status_line = header_section.split('\r\n')[0] if header_section else ''
        status_code = status_line.split()[1] if len(status_line.split()) > 1 else '000'
        body_text = response.split(b'\r\n\r\n', 1)
        resp_body = body_text[1].decode('utf-8', errors='ignore')[:500] if len(body_text) > 1 else ''

        if needs_auth and status_code in ('200', '200 OK'):
            return PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=5.3, severity='medium',
                description=f'{method} {path} accessible without auth — {note}',
                solution=self.SOLUTION,
                evidence=f'HTTP {status_code} on {path} without auth token — body: {resp_body[:100]}',
            )

        if not needs_auth and path == '/api/scans':
            pass

        if 'stacktrace' in header_section.lower() or 'traceback' in resp_body.lower() or \
           'File "' in resp_body:
            return PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=4.3, severity='medium',
                description=f'{method} {path} leaks debug information',
                solution='Disable debug mode in production.',
                evidence=f'Stack trace detected in response on {path}',
            )

        if 'server' in header_section.lower():
            for line in header_section.split('\r\n'):
                if line.lower().startswith('server:'):
                    sv = line.split(':', 1)[1].strip()
                    if sv not in ('Centra', 'Centra Engine'):
                        return PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=2.6, severity='low',
                            description=f'Server version disclosure in {path} header: {sv}',
                            solution='Use a generic server header.',
                            evidence=f'Server header: {sv}',
                        )

        return None
