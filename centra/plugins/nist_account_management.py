"""
Plugin 1063: NIST 800-53 AC-2 — Account Management
======================================================
NIST SP 800-53 Rev.5 AC-2: Account management controls for identifying,
authorizing, reviewing, and disabling accounts.
CVSS 8.9 — High: poor account management enables persistent unauthorized access.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class NistAccountManagement(NaslPlugin):
    PLUGIN_ID = 1063
    NAME = 'NIST 800-53 AC-2 — Account Management'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 8.9
    DESCRIPTION = (
        'NIST SP 800-53 AC-2 requires organizations to manage information '
        'system accounts throughout their lifecycle: creation, modification, '
        'review, disablement, and removal. This plugin checks account '
        'management controls on the target system.'
    )
    SOLUTION = (
        'Implement account lifecycle management: automated account creation '
        'with approval, periodic access reviews (quarterly), disabling inactive '
        'accounts (45 days), and removing terminated user access immediately. '
        'Use role-based access control (RBAC) with least privilege.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_admin_accounts(target, port))
        findings.extend(await self._check_registration_controls(target, port))
        findings.extend(await self._check_account_review(target, port))
        findings.extend(await self._check_inactive_accounts(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'NIST AC-2: {len(findings)} finding(s) — account management gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://csrc.nist.gov/glossary/term/AC-2', 'https://www.tenable.com/plugins/nessus/10497']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='NIST AC-2: Account management controls compliant')]

    async def _check_admin_accounts(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for user in ['admin', 'administrator', 'root', 'superadmin']:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                body = json.dumps({'username': user, 'password': 'centra2026'}).encode()
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
                            cvss_score=8.9, severity='high',
                            description=f'Privileged account "{user}" exists with known/default password',
                            solution='Remove or rename default admin accounts. Use individual named accounts.',
                            evidence=f'Account "{user}" authenticates successfully'))
                        return r
            except: pass
        return r

    async def _check_registration_controls(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': f'test_{port}', 'password': 'Test123!', 'display_name': 'T', 'company_id': 't'}).encode()
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
            body_t = resp.split(b'\r\n\r\n', 1)
            if '201' in status or '200' in status:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=6.5, severity='medium',
                    description='Self-registration allowed without approval — violates NIST AC-2(1)',
                    solution='Require approval for account creation. Implement invite-only registration.',
                    evidence='Account self-registration succeeded without admin approval'))
        except: pass
        return r

    async def _check_account_review(self, target: str, port: int) -> list[PluginResult]:
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
                    req2 = f'GET /api/users HTTP/1.1\r\nHost: {target}:{port}\r\nAuthorization: Bearer {tok}\r\nConnection: close\r\n\r\n'
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
                            cvss_score=5.3, severity='medium',
                            description='No account review/listing endpoint — cannot perform access reviews',
                            solution='Implement account review API for periodic access certification.',
                            evidence='GET /api/users returned 404'))
        except: pass
        return r

    async def _check_inactive_accounts(self, target: str, port: int) -> list[PluginResult]:
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
                    import base64, time
                    parts = tok.split('.')
                    payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                    exp = payload.get('exp', 0)
                    if exp == 0:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=7.5, severity='high',
                            description='Non-expiring tokens — accounts never auto-disabled',
                            solution='Implement token expiration and session timeouts.',
                            evidence='JWT has no expiration (exp=0)'))
        except: pass
        return r
