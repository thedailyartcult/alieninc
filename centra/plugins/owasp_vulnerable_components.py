"""
Plugin 1071: OWASP Top 10 A06 — Vulnerable & Outdated Components
====================================================================
OWASP Top 10 2021 A06: Using components with known vulnerabilities.
Checks the Centra engine itself for outdated components, libraries,
and dependencies with known CVEs.
CVSS 6.1 — Medium: vulnerable components enable easy exploitation.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class OwaspVulnerableComponents(NaslPlugin):
    PLUGIN_ID = 1071
    NAME = 'OWASP Top 10 A06 — Vulnerable Components'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'OWASP Top 10 2021 A06 (formerly A9) covers using components '
        'with known vulnerabilities. This plugin checks the Centra engine '
        'for outdated frameworks, libraries, and exposed component versions '
        'that may have known CVEs.'
    )
    SOLUTION = (
        'Keep all components up to date. Remove unused dependencies. '
        'Monitor CVE feeds for library vulnerabilities. Use a software '
        'bill of materials (SBOM). Automate dependency scanning in CI/CD.'
    )
    PORTS = [80, 443, 8721]

    VULNERABLE_COMPONENTS = [
        ('fastapi', '0.100.0'),
        ('uvicorn', '0.24.0'),
        ('python', '3.12.0'),
    ]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_response_headers(target, port))
        findings.extend(await self._check_api_disclosure(target, port))
        findings.extend(await self._check_dependency_exposure(target, port))
        findings.extend(await self._check_vulnerable_headers(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='medium',
                description=f'OWASP A06: {len(findings)} finding(s) — vulnerable component indicators',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='OWASP A06: No vulnerable component indicators detected')]

    async def _check_response_headers(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            req = f'GET / HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode())
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 8192: break
            wr.close()
            hdr = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            for ln in hdr.split('\r\n'):
                for comp, min_ver in self.VULNERABLE_COMPONENTS:
                    if comp in ln.lower():
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.0, severity='medium',
                            description=f'Component version exposed in headers: {ln.strip()}',
                            solution='Remove version information from response headers.',
                            evidence=f'Header: {ln.strip()}'))
        except: pass
        return r

    async def _check_api_disclosure(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for doc_path in ['/docs', '/redoc', '/openapi.json', '/api/docs']:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                req = f'GET {doc_path} HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
                wr.write(req.encode())
                await wr.drain()
                resp = b''
                while True:
                    c = await asyncio.wait_for(rd.read(4096), timeout=3)
                    if not c: break
                    resp += c
                    if len(resp) > 16384: break
                wr.close()
                status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '200' in status or '301' in status or '302' in status:
                    body_t = resp.split(b'\r\n\r\n', 1)
                    text = body_t[1].decode('utf-8', errors='ignore')[:2000] if len(body_t) > 1 else ''

                    versions_found = []
                    import re
                    for match in re.finditer(r'"version"\s*:\s*"([^"]+)"', text):
                        versions_found.append(match.group(1))
                    for match in re.finditer(r'FastAPI|Uvicorn|Starlette|Pydantic', text, re.IGNORECASE):
                        versions_found.append(match.group(0))

                    if versions_found:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.1, severity='medium',
                            description=f'API documentation exposes component versions: {", ".join(set(versions_found))}',
                            solution='Disable API docs in production. Remove version strings.',
                            evidence=f'{doc_path} exposes: {", ".join(set(versions_found)[:5])}',
                            references=['https://www.tenable.com/plugins/nessus/10497']))
                    break
            except: pass
        return r

    async def _check_dependency_exposure(self, target: str, port: int) -> list[PluginResult]:
        r = []
        sensitive_paths = [
            '/requirements.txt', '/package.json', '/Pipfile', '/Pipfile.lock',
            '/poetry.lock', '/pyproject.toml', '/package-lock.json',
            '/composer.json', '/go.mod', '/Cargo.toml',
            '/.env', '/config.py', '/app.py',
        ]
        for path in sensitive_paths:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                req = f'GET {path} HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
                wr.write(req.encode())
                await wr.drain()
                resp = b''
                while True:
                    c = await asyncio.wait_for(rd.read(4096), timeout=3)
                    if not c: break
                    resp += c
                    if len(resp) > 8192: break
                wr.close()
                status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '200' in status:
                    body_t = resp.split(b'\r\n\r\n', 1)
                    text = body_t[1].decode('utf-8', errors='ignore')[:500] if len(body_t) > 1 else ''
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=6.1, severity='medium',
                        description=f'Dependency file exposed: {path}',
                        solution='Remove dependency files from public access.',
                        evidence=f'GET {path} returned HTTP 200 — content: {text[:80]}...',
                        references=['https://www.tenable.com/plugins/nessus/10428']))
            except: pass
        return r

    async def _check_vulnerable_headers(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            req = f'GET / HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode())
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 4096: break
            wr.close()
            hdr = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()

            for ln in hdr.split('\r\n'):
                if ln.startswith('x-powered-by:'):
                    tech = ln.split(':', 1)[1].strip()
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=4.0, severity='medium',
                        description=f'Technology stack disclosed via X-Powered-By: {tech}',
                        solution='Remove X-Powered-By header to hide technology stack.',
                        evidence=f'X-Powered-By: {tech}'))
        except: pass
        return r
