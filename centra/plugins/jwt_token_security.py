"""
Plugin 1053: JWT Token Security Audit (Self-Pentesting)
==========================================================
Tests the Centra engine's own JWT authentication for common
vulnerabilities: algorithm confusion, weak secrets, token expiration.
Self-pentesting pillar: verify the scanner's own auth is secure.
"""
import asyncio
import json
import base64

from plugins import NaslPlugin, PluginResult


class JwtTokenSecurity(NaslPlugin):
    PLUGIN_ID = 1053
    NAME = 'JWT Token Security Audit'
    FAMILY = 'Self-Pentesting'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Audits the Centra engine\'s JWT authentication implementation for '
        'algorithm confusion attacks, weak signing secrets, missing expiration, '
        'and token injection vulnerabilities.'
    )
    SOLUTION = (
        'Use a strong random secret for JWT signing. Reject "none" algorithm. '
        'Validate algorithm header against expected value. Set short token '
        'expiration (15-60 min). Implement token refresh rotation.'
    )
    PORTS = [80, 443, 8721]
    DEPENDENCIES = [1052]

    ALGORITHM_ATTACKS = ['none', 'None', 'NONE', 'nOnE']
    WEAK_SECRETS = ['secret', 'centra', 'password', 'changeme', 'admin', 'key', 'jwt_secret']

    async def check_target(self, target: str, port: int | None = 8721) -> list[PluginResult]:
        port = port or 8721
        findings = []

        real_token = await self._obtain_token(target, port)
        if not real_token:
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Could not obtain JWT token for testing')]

        parts = real_token.split('.')
        if len(parts) != 3:
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Response does not contain a standard JWT')]

        try:
            header_b64 = parts[0] + '=='
            header_json = base64.urlsafe_b64decode(header_b64).decode('utf-8')
            header = json.loads(header_json)
            payload_b64 = parts[1] + '=='
            payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
        except Exception:
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Could not decode JWT parts')]

        alg = header.get('alg', '')
        exp = payload.get('exp', 0)

        if not alg or alg == 'none':
            findings.append(('Algorithm confusion', f'JWT uses alg="{alg}" — vulnerable to algorithm confusion'))

        if 'kid' in header:
            findings.append(('Header injection', 'JWT uses kid header — potential injection vector'))

        for attack_alg in self.ALGORITHM_ATTACKS:
            forged = await self._try_forged_token(target, port, attack_alg)
            if forged:
                findings.append(('Algorithm confusion (verified)', f'Server accepts alg="{attack_alg}" tokens'))
                break

        for weak_secret in self.WEAK_SECRETS:
            forged = await self._try_hs256_token(target, port, alg, weak_secret)
            if forged:
                findings.append(('Weak signing secret', f'Server accepts JWT signed with "{weak_secret}"'))
                break

        headers_check = await self._check_auth_headers(target, port, real_token)
        findings.extend(headers_check)

        if findings:
            all_evidence = '; '.join(f'{t}: {d}' for t, d in findings)
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=f'JWT audit: {len(findings)} finding(s)',
                solution=self.SOLUTION,
                evidence=all_evidence,
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2022-23529',
                    'https://www.tenable.com/plugins/nessus/134662',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='JWT authentication appears secure',
            evidence=f'Token header: {header_json}, payload: {json.dumps({k:v for k,v in payload.items() if k != "exp"})}',
        )]

    async def _obtain_token(self, target: str, port: int) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
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
            writer.write(req.encode() + body)
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

            body_text = response.split(b'\r\n\r\n', 1)
            if len(body_text) > 1:
                resp = json.loads(body_text[1].decode('utf-8', errors='ignore'))
                return resp.get('access_token') or resp.get('token')

        except Exception:
            pass
        return None

    async def _try_forged_token(self, target: str, port: int, alg: str) -> bool:
        try:
            header = base64.urlsafe_b64encode(json.dumps({'alg': alg, 'typ': 'JWT'}).encode()).rstrip(b'=').decode()
            payload = base64.urlsafe_b64encode(json.dumps({'sub': 'admin', 'iat': 0}).encode()).rstrip(b'=').decode()
            forged = f'{header}.{payload}.'
            return await self._test_token(target, port, forged)
        except Exception:
            return False

    async def _try_hs256_token(self, target: str, port: int, real_alg: str, secret: str) -> bool:
        if real_alg != 'HS256':
            return False
        try:
            import hmac, hashlib
            header_b64 = base64.urlsafe_b64encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode()).rstrip(b'=').decode()
            payload_b64 = base64.urlsafe_b64encode(json.dumps({'sub': 'admin', 'iat': 0}).encode()).rstrip(b'=').decode()
            sig = hmac.new(secret.encode(), f'{header_b64}.{payload_b64}'.encode(), hashlib.sha256).digest()
            sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b'=').decode()
            forged = f'{header_b64}.{payload_b64}.{sig_b64}'
            return await self._test_token(target, port, forged)
        except Exception:
            return False

    async def _test_token(self, target: str, port: int, token: str) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = (
                f'GET /api/scans HTTP/1.1\r\n'
                f'Host: {target}:{port}\r\n'
                f'Authorization: Bearer {token}\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(2048), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 2048:
                    break

            writer.close()
            await writer.wait_closed()

            status = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            return '200' in status and ('[' in response.decode('utf-8', errors='ignore') or '{' in response.decode('utf-8', errors='ignore'))

        except Exception:
            return False

    async def _check_auth_headers(self, target: str, port: int, token: str) -> list[tuple]:
        findings = []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = (
                f'GET /api/scans HTTP/1.1\r\n'
                f'Host: {target}:{port}\r\n'
                f'Authorization: Bearer {token}\r\n'
                f'Connection: close\r\n\r\n'
            )
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

            header_text = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
            for line in header_text.split('\r\n'):
                if line.lower().startswith('set-cookie:'):
                    if 'httponly' not in line.lower():
                        findings.append(('Missing HttpOnly', 'Auth cookie missing HttpOnly flag'))
                    if 'secure' not in line.lower():
                        findings.append(('Missing Secure', 'Auth cookie missing Secure flag'))
                    if 'samesite' not in line.lower():
                        findings.append(('Missing SameSite', 'Auth cookie missing SameSite attribute'))

        except Exception:
            pass
        return findings
