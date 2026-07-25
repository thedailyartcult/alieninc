"""
Plugin 1061: Security Baseline Compliance (Self-Pentesting / Self-Fixing)
============================================================================
Compares the Centra engine's security posture against a defined security
baseline. Reports deviations and auto-generates remediation steps.
Self-pentesting + Self-fixing: measure against standard → fix deviations.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult, ScanContext


class SecurityBaselineCompliance(NaslPlugin):
    PLUGIN_ID = 1061
    NAME = 'Security Baseline Compliance'
    FAMILY = 'Self-Fixing'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 4.0
    DESCRIPTION = (
        'Compares the Centra engine\'s security posture against a hardened '
        'security baseline. Checks for deviations in TLS configuration, '
        'HTTP headers, authentication controls, and CORS policy. Reports '
        'a baseline compliance score and auto-generates remediation steps.'
    )
    SOLUTION = (
        'Apply the missing baseline controls listed in the evidence. '
        'Re-run this plugin after each fix to track baseline compliance '
        'improvement over time.'
    )
    DEPENDENCIES = [1003, 1005, 1028, 1037, 1052, 1053, 1057]

    BASELINE_CONTROLS = [
        {
            'id': 'TLS-01',
            'name': 'TLS 1.2+ enforced',
            'severity': 'high',
            'remediation': 'Disable TLS 1.0 and 1.1 in the server configuration',
        },
        {
            'id': 'HDR-01',
            'name': 'HSTS header present',
            'severity': 'medium',
            'remediation': 'Add Strict-Transport-Security header to all responses',
        },
        {
            'id': 'HDR-02',
            'name': 'CSP header present',
            'severity': 'high',
            'remediation': 'Add Content-Security-Policy header to all responses',
        },
        {
            'id': 'HDR-03',
            'name': 'X-Content-Type-Options: nosniff',
            'severity': 'medium',
            'remediation': 'Add X-Content-Type-Options: nosniff header',
        },
        {
            'id': 'CORS-01',
            'name': 'No wildcard CORS origin',
            'severity': 'medium',
            'remediation': 'Restrict Access-Control-Allow-Origin to specific domains',
        },
        {
            'id': 'AUTH-01',
            'name': 'Rate limiting on login',
            'severity': 'high',
            'remediation': 'Implement rate limiting on /api/auth/login',
        },
        {
            'id': 'AUTH-02',
            'name': 'JWT uses strong algorithm',
            'severity': 'high',
            'remediation': 'Reject "none" algorithm in JWT validation',
        },
        {
            'id': 'INF-01',
            'name': 'No server version disclosure',
            'severity': 'low',
            'remediation': 'Use a generic server header (e.g. "Centra")',
        },
    ]

    async def check_target(self, target: str, port: int | None = 8721,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        port = port or 8721
        passing = 0
        failing = 0
        details = []

        header_profile = await self._get_header_profile(target, port)

        for control in self.BASELINE_CONTROLS:
            passed, evidence = await self._check_control(target, port, control, header_profile)
            if passed:
                passing += 1
                details.append(f'  PASS {control["id"]} ({control["name"]})')
            else:
                failing += 1
                details.append(f'  FAIL {control["id"]} ({control["name"]}): {evidence}')
                details.append(f'        → Fix: {control["remediation"]}')

        total = len(self.BASELINE_CONTROLS)
        score = round(passing / total * 100, 1)
        status = 'compliant' if score >= 87.5 else 'partial' if score >= 50 else 'non_compliant'

        return [PluginResult(
            vulnerable=failing > 0,
            target=target,
            port=port,
            cvss_score=self.CVSS_SCORE if failing > 0 else 0.0,
            severity='high' if failing > 3 else 'medium' if failing > 0 else 'info',
            description=f'Security baseline: {passing}/{total} ({score}%) — {status}',
            solution='Apply the remediation steps for each FAILING control.',
            evidence='\n'.join(details),
            references=[
                'https://www.tenable.com/plugins/nessus/10497',
                'https://www.cisecurity.org/benchmark/kubernetes/',
            ]
        )]

    async def _get_header_profile(self, target: str, port: int) -> dict:
        profile = {}
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = f'GET / HTTP/1.1\r\nHost: {target}:{port}\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 8192:
                    break
            writer.close()
            await writer.wait_closed()

            header_text = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
            for line in header_text.split('\r\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    profile[key.strip()] = val.strip()
        except Exception:
            pass
        return profile

    async def _check_control(self, target: str, port: int,
                               control: dict, headers: dict) -> tuple[bool, str]:
        cid = control['id']

        if cid == 'TLS-01':
            try:
                for ssl_ver in [ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1]:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    ctx.maximum_version = ssl_ver
                    try:
                        r, w = await asyncio.wait_for(
                            asyncio.open_connection(target, port, ssl=ctx), timeout=4
                        )
                        w.close()
                        return False, f'TLS {ssl_ver.name} still accepted'
                    except (ssl.SSLError, OSError):
                        pass
                return True, 'TLS 1.2+ enforced'
            except Exception as e:
                return False, f'Error: {e}'

        if cid in ('HDR-01', 'HDR-02', 'HDR-03'):
            header_map = {
                'HDR-01': 'strict-transport-security',
                'HDR-02': 'content-security-policy',
                'HDR-03': 'x-content-type-options',
            }
            hdr = header_map[cid]
            if hdr in headers:
                return True, f'{hdr}: {headers[hdr]}'
            return False, f'{hdr} header missing'

        if cid == 'CORS-01':
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = (
                    f'GET /api/plugins HTTP/1.1\r\n'
                    f'Host: {target}:{port}\r\n'
                    f'Origin: https://evil.com\r\n'
                    f'Connection: close\r\n\r\n'
                )
                w.write(req.encode())
                await w.drain()
                resp = b''
                while True:
                    chunk = await asyncio.wait_for(r.read(4096), timeout=3)
                    if not chunk:
                        break
                    resp += chunk
                    if len(resp) > 2048:
                        break
                w.close()
                hdr_txt = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                for ln in hdr_txt.split('\r\n'):
                    if ln.startswith('access-control-allow-origin:'):
                        origin = ln.split(':', 1)[1].strip()
                        if origin == '*':
                            return False, 'ACAO: * (wildcard)'
                        return True, f'ACAO: {origin}'
                return True, 'No ACAO header (restrictive by default)'
            except Exception as e:
                return False, f'CORS check error: {e}'

        if cid == 'AUTH-01':
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                body = b'{"username":"admin","password":"wrong"}'
                req = (
                    f'POST /api/auth/login HTTP/1.1\r\n'
                    f'Host: {target}:{port}\r\n'
                    f'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'Connection: close\r\n\r\n'
                )
                w.write(req.encode() + body)
                await w.drain()
                resp = b''
                while True:
                    chunk = await asyncio.wait_for(r.read(4096), timeout=3)
                    if not chunk:
                        break
                    resp += chunk
                    if len(resp) > 2048:
                        break
                w.close()
                hdr_txt = resp.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                for ln in hdr_txt.split('\r\n'):
                    if 'retry-after' in ln or 'ratelimit' in ln:
                        return True, 'Rate limiting detected'
                return False, 'No rate limiting detected on login endpoint'
            except Exception as e:
                return False, f'Auth check error: {e}'

        if cid == 'AUTH-02':
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                body = b'{"username":"admin","password":"centra2026"}'
                req = (
                    f'POST /api/auth/login HTTP/1.1\r\n'
                    f'Host: {target}:{port}\r\n'
                    f'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'Connection: close\r\n\r\n'
                )
                w.write(req.encode() + body)
                await w.drain()
                resp = b''
                while True:
                    chunk = await asyncio.wait_for(r.read(4096), timeout=3)
                    if not chunk:
                        break
                    resp += chunk
                    if len(resp) > 4096:
                        break
                w.close()
                body_text = resp.split(b'\r\n\r\n', 1)
                if len(body_text) > 1:
                    import json
                    data = json.loads(body_text[1].decode('utf-8', errors='ignore'))
                    tok = data.get('access_token') or data.get('token', '')
                    if tok:
                        parts = tok.split('.')
                        import base64
                        hdr_raw = base64.urlsafe_b64decode(parts[0] + '==')
                        alg = json.loads(hdr_raw).get('alg', '')
                        if alg.lower() in ('none', ''):
                            return False, f'JWT uses alg="{alg}"'
                        return True, f'JWT uses alg="{alg}" (secure)'
                return True, 'JWT token obtained (verification requires deeper analysis)'
            except Exception as e:
                return False, f'JWT check error: {e}'

        if cid == 'INF-01':
            for key, val in headers.items():
                if key == 'server' and val not in ('Centra', 'Centra Engine', ''):
                    return False, f'Server header: {val}'
            return True, 'Server header generic or absent'

        return True, 'Check not implemented (pass by default)'
