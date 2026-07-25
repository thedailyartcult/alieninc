"""
Plugin 1070: CCPA §1798.150 — Data Security
===============================================
CCPA §1798.150 requires businesses to implement reasonable security
procedures to protect consumer personal information.
CVSS 6.5 — Medium: security gaps enable data breaches with statutory liability.
"""
import asyncio
import json

from plugins import NaslPlugin, PluginResult


class CcpaDataSecurity(NaslPlugin):
    PLUGIN_ID = 1070
    NAME = 'CCPA §1798.150 — Data Security'
    FAMILY = 'Compliance & Audit'
    CVSS_SCORE = 6.5
    DESCRIPTION = (
        'CCPA §1798.150(a) requires businesses to implement and maintain '
        'reasonable security procedures and practices to protect consumers\' '
        'personal information. This plugin checks for data protection controls, '
        'access controls, and incident response readiness.'
    )
    SOLUTION = (
        'Implement reasonable security: encrypt personal data, restrict '
        'access, log access events, maintain incident response plan, '
        'and conduct regular security testing. Update privacy policy '
        'with data collection practices per CCPA requirements.'
    )
    PORTS = [80, 443, 8721]

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        findings.extend(await self._check_privacy_policy(target, port))
        findings.extend(await self._check_data_access_controls(target, port))
        findings.extend(await self._check_incident_response(target, port))
        findings.extend(await self._check_consumer_rights(target, port))

        if findings:
            return [PluginResult(
                vulnerable=True, target=target, port=port,
                cvss_score=self.CVSS_SCORE, severity='medium',
                description=f'CCPA §1798.150: {len(findings)} finding(s) — data security gaps',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings),
                references=['https://oag.ca.gov/privacy/ccpa']
            )]

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='CCPA §1798.150: Data security practices compliant')]

    async def _check_privacy_policy(self, target: str, port: int) -> list[PluginResult]:
        r = []
        for pp_path in ['/privacy', '/privacy.html', '/privacy-policy', '/legal/privacy']:
            try:
                rd, wr = await asyncio.wait_for(asyncio.open_connection(target, port), timeout=5)
                req = f'GET {pp_path} HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
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
                if '200' in status:
                    body_t = resp.split(b'\r\n\r\n', 1)
                    text = body_t[1].decode('utf-8', errors='ignore').lower() if len(body_t) > 1 else ''
                    ccpa_terms = ['ccpa', 'california', 'do not sell', 'personal information', 'data subject',
                                   'right to know', 'right to delete', 'opt-out']
                    found = [t for t in ccpa_terms if t in text]
                    if len(found) < 3:
                        r.append(PluginResult(vulnerable=True, target=target, port=port,
                            cvss_score=5.0, severity='medium',
                            description=f'CCPA: Privacy policy missing required disclosures',
                            solution='Update privacy policy with CCPA-required disclosures.',
                            evidence=f'Found {len(found)}/{len(ccpa_terms)} required terms'))
                    break
            except: pass
        else:
            r.append(PluginResult(vulnerable=True, target=target, port=port,
                cvss_score=6.5, severity='medium',
                description='CCPA: No privacy policy accessible',
                solution='Publish privacy policy per CCPA requirements.',
                evidence='No privacy policy found at common paths'))
        return r

    async def _check_data_access_controls(self, target: str, port: int) -> list[PluginResult]:
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
                text = body_t[1].decode('utf-8', errors='ignore')
                if len(text) < 20:
                    r.append(PluginResult(vulnerable=True, target=target, port=port,
                        cvss_score=5.3, severity='medium',
                        description='CCPA: Minimal data returned — but no granular access control',
                        solution='Implement role-based data access for personal information.',
                        evidence='Auth response lacks user context for access decisions'))
        except: pass
        return r

    async def _check_incident_response(self, target: str, port: int) -> list[PluginResult]:
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
            body_t = resp.split(b'\r\n\r\n', 1)
            text = body_t[1].decode('utf-8', errors='ignore') if len(body_t) > 1 else ''
            if '200' in status and 'Contact' in text and 'Expires' in text:
                pass
            else:
                r.append(PluginResult(vulnerable=True, target=target, port=port,
                    cvss_score=4.0, severity='low',
                    description='CCPA: No adequate incident reporting channel',
                    solution='Publish security.txt with Contact and Expires for breach reporting.',
                    evidence='security.txt missing or incomplete'))
        except: pass
        return r

    async def _check_consumer_rights(self, target: str, port: int) -> list[PluginResult]:
        r = []
        dsr_paths = ['/data-subject-request', '/privacy/request', '/api/dsr', '/data-request']
        found_dsr = False
        for path in dsr_paths:
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
                    if len(resp) > 4096: break
                wr.close()
                status = resp.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                if '200' in status or '201' in status:
                    found_dsr = True
                    break
            except: pass

        if not found_dsr:
            r.append(PluginResult(vulnerable=True, target=target, port=port,
                cvss_score=5.3, severity='medium',
                description='CCPA: No data subject request mechanism found',
                solution='Implement DSR portal for Right to Know, Delete, and Opt-Out.',
                evidence='No consumer rights request endpoint detected'))
        return r
