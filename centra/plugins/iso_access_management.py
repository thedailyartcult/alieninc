"""
Plugin 1064: ISO 27001 A.9.2 — User Access Management
========================================================
ISO 27001:2022 Annex A Control 9.2: User access provisioning,
review, and removal of access rights.
CVSS 8.6 — High: unmanaged access enables data breaches.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class IsoAccessManagement(NaslPlugin):
    PLUGIN_ID = 1064
    NAME = 'ISO 27001 A.9.2 — User Access Management'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'ISO 27001 A.9.2 requires formal user access provisioning and '
        'de-provisioning processes. This plugin checks access control '
        'implementation: privileged access controls, access review capability, '
        'and removal of access on termination.'
    )
    SOLUTION = (
        'Implement RBAC with segregation of duties. Document access '
        'approval workflows. Automate access removal on termination. '
        'Conduct quarterly access reviews. Log all access changes.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_access_provisioning(target, port))
        findings.extend(await self._check_privilege_separation(target, port))
        findings.extend(await self._check_access_revocation(target, port))
        findings.extend(await self._check_access_logging(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'ISO 27001 A.9.2: {len(findings)} finding(s) — access management gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://www.iso.org/isoiec-27001-information-security/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='ISO 27001 A.9.2: Access management controls compliant')]

    async def _check_access_provisioning(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            for role in ['admin', 'user', 'viewer']:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                body = json.dumps({'username': f'test_{role}_{port}', 'password': 'Test123!', 'role': role, 'company_id': 't'}).encode()
                req = f'POST /api/auth/register HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
                wr.write(req.encode() + body)
                await wr.drain()
                resp = b''
                while True:
                    c = await asyncio.wait_for(rd.read(4096), timeout=3)
                    if not c: break
                    resp += c
                    if len(resp) > 2048: break
                wr.close()
                status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '201' in status or '200' in status:
                    page_content = resp.split(b'\r\n\r\n', 1)
                    text = page_content[1].decode('utf-8', errors='ignore') if len(page_content) > 1 else ''
                    if 'admin' in text.lower():
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=8.6, severity='high',
                            description=f'Self-registration allows assigning role="{role}" — violates segregation',
                            solution='Role assignment must require admin approval. No self-assigned privileges.',
                            evidence=f'Registration with role={role} succeeded'))
                        break
        except: pass
        return r

    async def _check_privilege_separation(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'centra2026'}).encode()
            req = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode() + body)
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 4096: break
            wr.close()
            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                tok = d.get('access_token') or d.get('token', '')
                if tok:
                    import base64
                    parts = tok.split('.')
                    payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                    if payload.get('sub') == 'admin' and 'role' not in payload:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.5, severity='medium',
                            description='No role/permission separation in JWT — all users have same privileges',
                            solution='Implement RBAC with distinct user roles encoded in tokens.',
                            evidence=f'JWT payload lacks role field: {json.dumps(payload)}'))
        except: pass
        return r

    async def _check_access_revocation(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'centra2026'}).encode()
            req = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode() + body)
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 4096: break
            wr.close()
            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                tok = d.get('access_token') or d.get('token', '')
                if tok:
                    for rev_path in ['/api/auth/revoke', '/api/auth/logout', '/api/users/revoke']:
                        try:
                            rd2, wr2 = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                            req2 = f'POST {rev_path} HTTP/1.1\r\nHost: {target}:{port}\r\nAuthorization: Bearer {tok}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                            wr2.write(req2.encode())
                            await wr2.drain()
                            resp2 = b''
                            while True:
                                c = await asyncio.wait_for(rd2.read(4096), timeout=3)
                                if not c: break
                                resp2 += c
                                if len(resp2) > 2048: break
                            wr2.close()
                            status2 = resp2.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                            if '404' in status2:
                                r.append(PluginResult(vulnerable=True, target=target, port=port,
                                    cvss_score=7.5, severity='high',
                                    description=f'No access revocation endpoint ({rev_path}) — cannot terminate sessions',
                                    solution='Implement token revocation and session termination endpoints.',
                                    evidence=f'POST {rev_path} returned HTTP 404'))
                        except: pass
        except: pass
        return r

    async def _check_access_logging(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'centra2026'}).encode()
            req = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode() + body)
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 4096: break
            wr.close()
            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                tok = d.get('access_token') or d.get('token', '')
                if tok:
                    rd2, wr2 = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                    req2 = f'GET /api/audit/log HTTP/1.1\r\nHost: {target}:{port}\r\nAuthorization: Bearer {tok}\r\nConnection: close\r\n\r\n'
                    wr2.write(req2.encode())
                    await wr2.drain()
                    resp2 = b''
                    while True:
                        c = await asyncio.wait_for(rd2.read(4096), timeout=3)
                        if not c: break
                        resp2 += c
                        if len(resp2) > 4096: break
                    wr2.close()
                    status2 = resp2.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                    if '404' in status2:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.5, severity='medium',
                            description='No audit log access — access events not reviewable',
                            solution='Implement audit logging for all access events per ISO 27001 A.12.4.',
                            evidence='GET /api/audit/log returned 404'))
        except: pass
        return r
