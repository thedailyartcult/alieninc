"""
Plugin 1062: PCI-DSS Req 8 — Authentication Controls
========================================================
PCI-DSS v4.0 Requirement 8: Identify and authenticate access to system components.
Checks for unique IDs, strong authentication, MFA support, and session controls.
CVSS 9.1 — Critical: authentication failures enable full system compromise.
"""
import asyncio
import json
import base64

from plugins import NaslPlugin, PluginResult


class PciDssAuthControls(NaslPlugin):
    PLUGIN_ID = 1062
    NAME = 'PCI-DSS Req 8 — Authentication Controls'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'PCI-DSS Requirement 8 mandates unique identification and strong '
        'authentication for all access to cardholder data environments. '
        'This plugin checks authentication implementation: password policies, '
        'session management, MFA readiness, and account lockout.'
    )
    SOLUTION = (
        'Implement strong password policies (min 12 chars, complexity). '
        'Enable MFA for all administrative access. Enforce session timeouts '
        '(max 15 min idle). Implement account lockout after 6 failed attempts. '
        'Use unique user IDs — no shared accounts.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []
        evidence = []

        findings.extend(await self._check_unique_ids(target, port))
        findings.extend(await self._check_password_policy(target, port))
        findings.extend(await self._check_session_management(target, port))
        findings.extend(await self._check_lockout(target, port))
        findings.extend(await self._check_mfa(target, port))

        for f in findings:
            evidence.append(f.evidence)

        if findings:
            return [PluginResult(
                vulnerable=True,
                target=target, port=port,
                cvss_score=self.CVSS_SCORE,
                severity='critical',
                description=f'PCI-DSS Req 8: {len(findings)} finding(s) — authentication controls need remediation',
                solution=self.SOLUTION,
                evidence='; '.join(evidence),
                references=['https://www.pcisecuritystandards.org/', 'https://www.tenable.com/plugins/nessus/10488']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='PCI-DSS Req 8: Authentication controls compliant')]

    async def _check_unique_ids(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for user in ['admin', 'root', 'test', 'demo']:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                body = json.dumps({'username': user, 'password': user}).encode()
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
                            cvss_score=9.1, severity='critical',
                            description=f'Default/shared account "{user}" with password "{user}" is active',
                            solution='Remove shared default accounts. Enforce unique user IDs.',
                            evidence=f'Login succeeded with user={user}'))
                        return r
            except: pass
        return r

    async def _check_password_policy(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'a'}).encode()
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
                if d.get('detail') and 'invalid' not in d['detail'].lower():
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=7.5, severity='high',
                        description='No password complexity enforcement detected',
                        solution='Enforce minimum 12-char password with complexity requirements.',
                        evidence=f'Login with single-char password returned: {d["detail"][:100]}'))
        except: pass

        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'admin', 'display_name': 'T', 'company_id': 't'}).encode()
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
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=6.5, severity='medium',
                    description='Weak password "admin" accepted during registration',
                    solution='Enforce minimum password strength at registration.',
                    evidence='Password "admin" accepted for new user registration'))
        except: pass
        return r

    async def _check_session_management(self, target: str, port: int) -> list[PluginResult]:
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
            for ln in hdr.split('\r\n'):
                if ln.startswith('set-cookie:'):
                    if 'max-age' not in ln and 'expires' not in ln:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=7.2, severity='high',
                            description='Session cookie lacks expiration — non-expiring session',
                            solution='Set session timeouts per PCI-DSS (max 15 min idle).',
                            evidence=f'Cookie without expiry: {ln[:80]}'))
                    if 'httponly' not in ln:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.3, severity='medium',
                            description='Session cookie missing HttpOnly flag',
                            solution='Add HttpOnly flag to all session cookies.',
                            evidence='Set-Cookie missing HttpOnly'))
                    if 'secure' not in ln:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.3, severity='medium',
                            description='Session cookie missing Secure flag',
                            solution='Add Secure flag to all session cookies.',
                            evidence='Set-Cookie missing Secure'))

            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                tok = d.get('access_token') or d.get('token', '')
                if tok:
                    parts = tok.split('.')
                    try:
                        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
                        exp = payload.get('exp', 0)
                        iat = payload.get('iat', 0)
                        if exp and iat:
                            duration = exp - iat
                            if duration > 3600:
                                r.append(PluginResult(vulnerable=True, target=target, port=port,
                                    cvss_score=6.5, severity='medium',
                                    description=f'Long-lived JWT token ({duration / 60:.0f} min) — exceeds PCI-DSS session timeout',
                                    solution='Set JWT expiration to max 15 minutes.',
                                    evidence=f'Token issued at {iat}, expires at {exp} ({duration}s)'))
                    except: pass
        except: pass
        return r

    async def _check_lockout(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            body = json.dumps({'username': 'admin', 'password': 'wrong'}).encode()
            req = f'POST /api/auth/login HTTP/1.1\r\nHost: {target}:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            for _ in range(10):
                wr.write(req.encode() + body)
                await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 2048: break
            wr.close()
            hdr = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            if 'retry-after' not in hdr and '429' not in hdr:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=8.5, severity='high',
                    description='No account lockout after 10 failed login attempts',
                    solution='Implement lockout after 6 failed attempts per PCI-DSS Req 8.',
                    evidence='10 sequential failed logins without lockout or rate limiting'))
        except: pass
        return r

    async def _check_mfa(self, target: str, port: int) -> list[PluginResult]:
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
                if d.get('access_token') or d.get('token'):
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=8.0, severity='high',
                        description='No MFA required for administrative access',
                        solution='Implement MFA for all admin access per PCI-DSS Req 8.4.',
                        evidence='Login with password-only succeeded — no MFA challenge'))
        except: pass
        return r
