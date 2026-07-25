"""
Plugin 1066: SOC 2 CC6.1 — Logical Access Security
======================================================
SOC 2 Type II CC6.1: Logical and physical access controls to
protect information assets against unauthorized access.
CVSS 7.8 — High: access control failures lead to data loss.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class Soc2LogicalAccess(NaslPlugin):
    PLUGIN_ID = 1066
    NAME = 'SOC 2 CC6.1 — Logical Access Security'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 7.8
    DESCRIPTION = (
        'SOC 2 CC6.1 requires controls to prevent, detect, and deter '
        'unauthorized logical access to information assets. This plugin '
        'checks authentication strength, access logging, and session controls.'
    )
    SOLUTION = (
        'Implement strong authentication (MFA, complex passwords). Log all '
        'access attempts. Enforce session timeouts. Review access quarterly. '
        'Use encryption for data in transit and at rest.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_authentication(target, port))
        findings.extend(await self._check_access_logging(target, port))
        findings.extend(await self._check_session_controls(target, port))
        findings.extend(await self._check_tls_access(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'SOC 2 CC6.1: {len(findings)} finding(s) — logical access gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://www.aicpa.org/trust-services/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='SOC 2 CC6.1: Logical access controls compliant')]

    async def _check_authentication(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for user, pw in [('admin', 'admin'), ('admin', 'password'), ('admin', 'centra2026'), ('admin', '12345')]:
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
                            cvss_score=7.8, severity='high',
                            description=f'Weak credentials accepted: {user}/{pw}',
                            solution='Enforce strong password policy. Disable common/weak passwords.',
                            evidence=f'Login with {user}/{pw} succeeded'))
                        return r
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
                    for log_path in ['/api/audit/logs', '/api/logs/access', '/api/access/log']:
                        try:
                            rd2, wr2 = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                            req2 = f'GET {log_path} HTTP/1.1\r\nHost: {target}:{port}\r\nAuthorization: Bearer {tok}\r\nConnection: close\r\n\r\n'
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
                            if '200' in status2:
                                break
                        except: pass
                    else:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.3, severity='medium',
                            description='No access log review capability — SOC 2 CC6.1 requires logging',
                            solution='Implement access logging with review capability.',
                            evidence='No audit/log access endpoints available'))
        except: pass
        return r

    async def _check_session_controls(self, target: str, port: int) -> list[PluginResult]:
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
            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                d = json.loads(body_t[1].decode('utf-8', errors='ignore'))
                tok = d.get('access_token') or d.get('token', '')
                if tok:
                    import base64
                    payload = json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
                    iat = payload.get('iat', 0)
                    exp = payload.get('exp', 0)
                    if iat and not exp:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=6.5, severity='medium',
                            description='No session expiration — sessions never time out',
                            solution='Implement session timeouts with absolute and idle expirations.',
                            evidence='JWT has iat but no exp'))
        except: pass
        return r

    async def _check_tls_access(self, target: str, port: int) -> list[PluginResult]:
        r = []
        if port and port != 443:
            return r
        import ssl
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            rd, wr = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            cert = wr.get_extra_info('peercert')
            wr.close()
            if cert:
                from datetime import datetime
                na = cert.get('notAfter', '')
                if na:
                    try:
                        exp_date = datetime.strptime(na, '%b %d %H:%M:%S %Y %Z')
                        if exp_date < datetime.utcnow():
                            r.append(PluginResult(vulnerable=True, target=target, port=port,
                                cvss_score=7.5, severity='high',
                                description='Expired TLS certificate — access security compromised',
                                solution='Renew TLS certificate immediately.',
                                evidence=f'Certificate expired: {na}'))
                    except: pass
        except: pass
        return r
