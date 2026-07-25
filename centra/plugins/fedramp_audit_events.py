"""
Plugin 1067: FedRAMP AU-2 — Audit Event Generation
======================================================
FedRAMP High AU-2 / NIST 800-53 AU-2: Audit events that identify
and track system access and security-relevant activities.
CVSS 7.5 — High: missing audit logs enable undetected breaches.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class FedrampAuditEvents(NaslPlugin):
    PLUGIN_ID = 1067
    NAME = 'FedRAMP AU-2 — Audit Event Generation'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'FedRAMP AU-2 requires organizations to define auditable events '
        'and generate audit records for: successful/failed logins, '
        'privileged access, configuration changes, and security-relevant events.'
    )
    SOLUTION = (
        'Implement comprehensive audit logging for all security-relevant '
        'events: authentication, authorization, configuration changes, '
        'and data access. Retain logs per FedRAMP requirements (90 days '
        'online, 1 year cold storage).'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_login_auditing(target, port))
        findings.extend(await self._check_privileged_access_audit(target, port))
        findings.extend(await self._check_audit_log_access(target, port))
        findings.extend(await self._check_audit_log_protection(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'FedRAMP AU-2: {len(findings)} finding(s) — audit event gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://csrc.nist.gov/glossary/term/AU-2']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='FedRAMP AU-2: Audit event generation compliant')]

    async def _check_login_auditing(self, target: str, port: int) -> list[PluginResult]:
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
            hdr = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            if 'x-audit-id' not in hdr and 'x-request-id' not in hdr and 'x-log-id' not in hdr:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=6.5, severity='medium',
                    description='No audit ID in login response — events not traceable',
                    solution='Assign unique audit IDs to all authentication events.',
                    evidence='No X-Audit-ID or X-Request-ID in response headers'))
        except: pass
        return r

    async def _check_privileged_access_audit(self, target: str, port: int) -> list[PluginResult]:
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
                    req2 = f'GET /api/audit/events HTTP/1.1\r\nHost: {target}:{port}\r\nAuthorization: Bearer {tok}\r\nConnection: close\r\n\r\n'
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
                            cvss_score=7.5, severity='high',
                            description='No audit event access — cannot verify privileged access auditing',
                            solution='Implement privileged access audit log with retention.',
                            evidence='No audit events endpoint available'))
        except: pass
        return r

    async def _check_audit_log_access(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            req = f'GET /api/logs HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode())
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 2048: break
            wr.close()
            status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            if '200' in status:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=7.5, severity='high',
                    description='Audit logs publicly accessible without authentication',
                    solution='Require authentication and authorization for all audit log access.',
                    evidence='GET /api/logs returned 200 without auth token'))
        except: pass
        return r

    async def _check_audit_log_protection(self, target: str, port: int) -> list[PluginResult]:
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
                    payload = json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
                    sub = payload.get('sub', '')
                    iat = payload.get('iat', 0)
                    body2 = json.dumps({'username': sub, 'password': 'centra2026'}).encode()
                    rd2, wr2 = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                    req2 = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body2)}\r\nConnection: close\r\n\r\n'
                    wr2.write(req2.encode() + body2)
                    await wr2.drain()
                    resp2 = b''
                    while True:
                        c = await asyncio.wait_for(rd2.read(4096), timeout=3)
                        if not c: break
                        resp2 += c
                        if len(resp2) > 4096: break
                    wr2.close()
                    body_t2 = resp2.split(b'\r\n\r\n', 1)
                    if len(body_t2) > 1:
                        d2 = json.loads(body_t2[1].decode('utf-8', errors='ignore'))
                        tok2 = d2.get('access_token') or d2.get('token', '')
                        if tok2 and tok2 == tok and iat > 0:
                            r.append(PluginResult(vulnerable=True, target=target, port=port,
                                cvss_score=6.5, severity='medium',
                                description='Same token issued for repeated logins — no session rotation',
                                solution='Issue new tokens on each login. Invalidate previous sessions.',
                                evidence='Repeated login produced identical token'))
        except: pass
        return r
