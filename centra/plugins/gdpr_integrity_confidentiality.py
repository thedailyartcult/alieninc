"""
Plugin 1068: GDPR Art.5(1)(f) — Integrity & Confidentiality
==============================================================
GDPR Article 5(1)(f): Personal data shall be processed in a manner
that ensures appropriate security, integrity, and confidentiality.
CVSS 7.2 — High: integrity failures lead to data compromise.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class GdprIntegrityConfidentiality(NaslPlugin):
    PLUGIN_ID = 1068
    NAME = 'GDPR Art.5(1)(f) — Integrity & Confidentiality'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 7.2
    DESCRIPTION = (
        'GDPR Art.5(1)(f) requires appropriate technical measures to '
        'ensure ongoing integrity and confidentiality of personal data. '
        'This plugin checks TLS configuration, data exposure, and '
        'breach detection readiness.'
    )
    SOLUTION = (
        'Encrypt all personal data in transit (TLS 1.2+) and at rest. '
        'Implement breach detection and notification procedures. '
        'Regularly test security measures. Maintain data processing records.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_data_exposure(target, port))
        findings.extend(await self._check_tls_compliance(target, port))
        findings.extend(await self._check_breach_detection(target, port))
        findings.extend(await self._check_data_minimization(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='high',
                description=f'GDPR Art.5(1)(f): {len(findings)} finding(s) — integrity gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://gdpr.eu/article-5-principles/']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='GDPR Art.5(1)(f): Integrity & confidentiality compliant')]

    async def _check_data_exposure(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            req = f'GET /api/plugins HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            wr.write(req.encode())
            await wr.drain()
            resp = b''
            while True:
                c = await asyncio.wait_for(rd.read(4096), timeout=3)
                if not c: break
                resp += c
                if len(resp) > 65536: break
            wr.close()
            body_t = resp.split(b'\r\n\r\n', 1)
            if len(body_t) > 1:
                text = body_t[1].decode('utf-8', errors='ignore')
                if 'access_token' in text or 'token' in text or 'secret' in text:
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=7.2, severity='high',
                        description='Sensitive data (tokens/secrets) exposed in API response',
                        solution='Remove sensitive data from API responses. Mask secrets.',
                        evidence='Tokens or secrets found in API response body'))
        except: pass
        return r

    async def _check_tls_compliance(self, target: str, port: int) -> list[PluginResult]:
        r = []
        import ssl
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            rd, wr = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            cipher = wr.get_extra_info('cipher', ('', '', 0))
            cipher_name = cipher[0] if cipher else ''
            if cipher_name and any(w in cipher_name.lower() for w in ['rc4', 'des', 'md5', '3des']):
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=6.5, severity='medium',
                    description=f'Weak TLS cipher in use: {cipher_name}',
                    solution='Disable weak ciphers. Use AEAD ciphers (AES-GCM, ChaCha20).',
                    evidence=f'Negotiated cipher: {cipher_name}'))
            wr.close()
        except: pass
        return r

    async def _check_breach_detection(self, target: str, port: int) -> list[PluginResult]:
        r = []
        try:
            rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
            req = f'GET /.well-known/security.txt HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
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
            if '404' in status:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=5.0, severity='medium',
                    description='No security.txt — no breach reporting channel (GDPR Art.33)',
                    solution='Publish security.txt (RFC 9116) for breach disclosure.',
                    evidence='GET /.well-known/security.txt returned 404'))
            else:
                body_t = resp.split(b'\r\n\r\n', 1)
                text = body_t[1].decode('utf-8', errors='ignore') if len(body_t) > 1 else ''
                if 'Contact' not in text:
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=4.0, severity='low',
                        description=f'security.txt exists but missing "Contact" field',
                        solution='Include "Contact" field with responsible disclosure contact.',
                        evidence=f'security.txt content: {text[:100]}'))
        except: pass
        return r

    async def _check_data_minimization(self, target: str, port: int) -> list[PluginResult]:
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
                text = body_t[1].decode('utf-8', errors='ignore').lower()
                if 'email' in text or 'phone' in text or 'address' in text:
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=5.3, severity='medium',
                        description='Login API returns personal data (email/phone/address)',
                        solution='Minimize personal data in API responses per GDPR Art.5(1)(c).',
                        evidence=f'Personal data field found in login response'))
        except: pass
        return r
