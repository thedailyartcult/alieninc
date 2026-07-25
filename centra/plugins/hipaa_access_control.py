"""
Plugin 1065: HIPAA 164.312(a)(1) — Access Control
====================================================
HIPAA Security Rule 164.312(a)(1): Technical policies for electronic
protected health information (ePHI) access.
CVSS 8.2 — High: unauthorized ePHI access causes data breaches.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class HipaaAccessControl(NaslPlugin):
    PLUGIN_ID = 1065
    NAME = 'HIPAA 164.312(a)(1) — Access Control'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 8.2
    DESCRIPTION = (
        'HIPAA 164.312(a)(1) requires technical access controls for '
        'electronic protected health information (ePHI). This plugin '
        'checks for unique user identification, emergency access, '
        'automatic logoff, and encryption and decryption controls.'
    )
    SOLUTION = (
        'Assign unique user IDs to all ePHI system users. Implement '
        'emergency access procedure. Enforce automatic logoff after '
        '15 minutes of inactivity. Encrypt ePHI at rest and in transit.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_unique_user_id(target, port))
        findings.extend(await self._check_emergency_access(target, port))
        findings.extend(await self._check_automatic_logoff(target, port))
        findings.extend(await self._check_encryption_decryption(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'HIPAA 164.312(a)(1): {len(findings)} finding(s) — access control gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://www.hhs.gov/hipaa/for-professionals/security/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='HIPAA 164.312(a)(1): Access controls compliant')]

    async def _check_unique_user_id(self, target: str, port: int) -> list[PluginResult]:
        r = []
        if await self._check_shared_account(target, port, 'admin', 'centra2026'):
            r.append(PluginResult(vulnerable=True, target=target, port=port,
                cvss_score=8.2, severity='high',
                description='Shared admin account — violates HIPAA unique user ID requirement',
                solution='Replace shared accounts with individual named accounts.',
                evidence='Shared "admin" account used for authentication — no individual user tracking'))
        return r

    async def _check_shared_account(self, target: str, port: int, user: str, pw: str) -> bool:
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
                return bool(d.get('access_token') or d.get('token'))
        except: pass
        return False

    async def _check_emergency_access(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for em_path in ['/api/emergency/access', '/api/auth/emergency', '/break-glass']:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                req = f'GET {em_path} HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
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
                if '404' in status:
                    continue
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=7.5, severity='high',
                    description=f'Emergency access procedure not exposed ({em_path} returned 404)',
                    solution='Implement and document emergency access procedure per HIPAA 164.312(a)(1).',
                    evidence=f'Emergency access endpoint {em_path} not found'))
                return r
            except: pass

        if not r:
            r.append(PluginResult(vulnerable=True, target=target, port=port,
                cvss_score=7.5, severity='high',
                description='No emergency access procedure detected',
                solution='Implement break-glass emergency access with post-event audit.',
                evidence='No emergency/break-glass endpoints found'))
        return r

    async def _check_automatic_logoff(self, target: str, port: int) -> list[PluginResult]:
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
                    exp = payload.get('exp', 0)
                    iat = payload.get('iat', 0)
                    if exp and iat and (exp - iat) > 900:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.5, severity='medium',
                            description=f'Session timeout ({(exp-iat)//60} min) exceeds HIPAA 15-min max',
                            solution='Enforce automatic logoff after 15 minutes of inactivity.',
                            evidence=f'Token duration: {(exp-iat)//60} minutes'))
        except: pass
        return r

    async def _check_encryption_decryption(self, target: str, port: int) -> list[PluginResult]:
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
            scheme = 'https' if port == 443 else 'http'
            if scheme == 'http' and port != 443:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=8.2, severity='high',
                    description='Plain HTTP in use — ePHI transmitted without encryption',
                    solution='Enforce TLS for all ePHI transmissions per HIPAA 164.312(e)(1).',
                    evidence=f'Connection on port {port} uses unencrypted HTTP'))
        except: pass
        return r
