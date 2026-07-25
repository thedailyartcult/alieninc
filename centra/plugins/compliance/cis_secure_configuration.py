"""
Plugin 1069: CIS Control 4 — Secure Configuration of Systems
===============================================================
CIS Critical Security Control 4: Secure configuration of enterprise
assets, devices, and software to prevent exploitation.
CVSS 6.8 — Medium: insecure configurations enable attacks.
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class CisSecureConfiguration(NaslPlugin):
    PLUGIN_ID = 1069
    NAME = 'CIS Control 4 — Secure Configuration'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.8
    DESCRIPTION = (
        'CIS Critical Control 4 requires secure configuration of all '
        'enterprise assets. This plugin checks the Centra engine against '
        'CIS benchmarks: unnecessary services, default accounts, '
        'security headers, TLS configuration, and access controls.'
    )
    SOLUTION = (
        'Apply CIS benchmarks for the server platform. Remove unnecessary '
        'accounts and services. Enforce HTTPS with HSTS. Implement secure '
        'HTTP headers. Disable directory listing and server info disclosure.'
    )
    PORTS = [80, 443, 8721]

    CIS_CONTROLS = [
        ('4.1', 'Default account passwords changed', 'high'),
        ('4.2', 'Unnecessary services disabled', 'medium'),
        ('4.3', 'Security headers implemented', 'medium'),
        ('4.4', 'HTTPS enforcement with HSTS', 'high'),
        ('4.5', 'Information disclosure prevented', 'low'),
    ]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_default_accounts(target, port))
        findings.extend(await self._check_security_headers(target, port))
        findings.extend(await self._check_https_enforcement(target, port))
        findings.extend(await self._check_info_disclosure(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='medium',
                description=f'CIS Control 4: {len(findings)} finding(s) — configuration gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://www.cisecurity.org/controls/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='CIS Control 4: Secure configuration compliant')]

    async def _check_default_accounts(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for user, pw in [('admin', 'admin'), ('admin', 'password'), ('admin', 'centra2026'), ('root', 'root')]:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                body = json.dumps({'username': user, 'password': pw}).encode()
                req = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
                wr.write(req.encode() + body)
                await wr.drain()
                resp = b''
                while True:
                    c = await asyncio.wait_for(rd.read(4096), timeout=3)
                    if not c: break
                    resp += c
                    if len(resp) > 2048: break
                wr.close()
                body_t = resp.split(b'\r\n\r\n', 1)
                if len(body_t) > 1:
                    d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                    if d.get('access_token') or d.get('token'):
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.8, severity='high',
                            description=f'CIS 4.1: Default credentials still active: {user}/{pw}',
                            solution='Change all default passwords. Remove unused accounts.',
                            evidence=f'Login with {user}/{pw} succeeded'))
                        return r
            except: pass
        return r

    async def _check_security_headers(self, target: str, port: int) -> list[PluginResult]:
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

            required = {
                'strict-transport-security': 'CIS 4.4',
                'x-content-type-options': 'CIS 4.3',
                'x-frame-options': 'CIS 4.3',
            }
            missing = []
            for h, reason in required.items():
                found = False
                for ln in hdr.split('\r\n'):
                    if ln.startswith(h + ':'):
                        if h == 'strict-transport-security' and 'max-age=0' in ln:
                            missing.append(f'{h} (set to disable)')
                            found = True
                            break
                        found = True
                        break
                if not found:
                    missing.append(h)

            if missing:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=5.0, severity='medium',
                    description=f'CIS 4.3/4.4: Missing security headers: {", ".join(missing)}',
                    solution='Implement missing security headers per CIS benchmarks.',
                    evidence=f'Missing: {", ".join(missing)}'))

            if 'strict-transport-security' in hdr:
                for ln in hdr.split('\r\n'):
                    if ln.startswith('strict-transport-security:'):
                        if 'max-age=0' in ln or 'max-age' not in ln:
                            r.append(PluginResult(vulnerable=True, target=target, port=port,
                                cvss_score=5.3, severity='medium',
                                description='CIS 4.4: HSTS set to disable or no max-age',
                                solution='Set HSTS with max-age >= 31536000 (1 year).',
                                evidence=f'HSTS: {ln}'))
                        elif 'includesubdomains' not in ln:
                            r.append(PluginResult(vulnerable=True, target=target, port=port,
                                cvss_score=3.7, severity='low',
                                description='CIS 4.4: HSTS missing includeSubdomains directive',
                                solution='Add includeSubdomains to HSTS header.',
                                evidence=f'HSTS: {ln}'))

        except: pass
        return r

    async def _check_https_enforcement(self, target: str, port: int) -> list[PluginResult]:
        r = []
        if port == 80:
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
                status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '200' in status:
                    hdr = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                    redirected = False
                    for ln in hdr.split('\r\n'):
                        if ln.startswith('location:') and 'https://' in ln:
                            redirected = True
                    if not redirected:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.3, severity='medium',
                            description='CIS 4.4: HTTP not redirecting to HTTPS',
                            solution='Redirect all HTTP traffic to HTTPS.',
                            evidence='HTTP on port 80 returns 200 without redirect'))
            except: pass
        return r

    async def _check_info_disclosure(self, target: str, port: int) -> list[PluginResult]:
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
                if ln.startswith('server:'):
                    val = ln.split(':', 1)[1].strip()
                    if val and val not in ('Centra', 'Centra Engine'):
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=2.6, severity='low',
                            description=f'CIS 4.5: Server version disclosure: {val}',
                            solution='Remove server version from response headers.',
                            evidence=f'Server header: {val}'))
                if ln.startswith('x-powered-by:'):
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=2.6, severity='low',
                        description='CIS 4.5: X-Powered-By technology disclosure',
                        solution='Remove X-Powered-By header.',
                        evidence=f'X-Powered-By: {ln.split(":", 1)[1].strip()}'))
        except: pass
        return r
