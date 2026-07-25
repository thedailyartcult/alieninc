"""
Plugin 1126: JWT Weak HMAC Secret Detection
==============================================
Tests JWT tokens for weak/guessable HMAC signing secrets.
CVE-2016-5431: JWT algorithm confusion and weak secret attacks.
"""
import asyncio
import base64
import json
import ssl

from plugins import NaslPlugin, PluginResult


class JwtWeakSecretDetection(NaslPlugin):
    PLUGIN_ID = 1126
    NAME = 'JWT Weak HMAC Secret Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Detects JWT tokens signed with weak or guessable HMAC secrets. '
        'Tests common weak secrets (secret, password, jwt, key, changeme) '
        'against JWT tokens found in responses. If a weak secret is cracked, '
        'attackers can forge arbitrary tokens and impersonate any user.'
    )
    SOLUTION = (
        'Use strong, randomly generated secrets (256+ bits). Use asymmetric '
        'algorithms (RS256/ES256). Rotate signing keys regularly.'
    )
    CVE = ['CVE-2016-5431']
    PORTS = [80, 443, 8080, 8443]

    WEAK_SECRETS = ['secret', 'password', 'jwt', 'key', 'changeme']
    JWT_REGEX = rb'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'

    PROBE_PATHS = ['/', '/api/', '/api/v1/', '/auth/', '/login', '/api/auth/']

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ports = self.PORTS if port is None else [port]

        for p in ports:
            try:
                scheme = 'https' if p in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                tokens = []
                for path in self.PROBE_PATHS:
                    token = await self._fetch_jwt_token(target, p, path, ctx)
                    if token:
                        tokens.append(token)
                    if len(tokens) >= 3:
                        break

                if not tokens:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No JWT tokens found in responses'
                    ))
                    continue

                cracked = []
                for token in set(tokens):
                    for secret in self.WEAK_SECRETS:
                        if await self._try_weak_secret(token, secret):
                            cracked.append((token[:40], secret))
                            break

                if cracked:
                    token_evidence = '; '.join(f'token={t} secret={s}' for t, s in cracked)
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='critical',
                        description=f'JWT weak secret: {len(cracked)} token(s) cracked with weak HMAC secrets',
                        solution=self.SOLUTION,
                        evidence=token_evidence,
                        references=[
                            'https://nvd.nist.gov/vuln/detail/CVE-2016-5431',
                            'https://www.tenable.com/plugins/nessus/134662',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description=f'JWT tokens found but not cracked with common weak secrets'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _fetch_jwt_token(self, target: str, port: int, path: str, ctx: ssl.SSLContext | None) -> str | None:
        try:
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                f'eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QifQ.'
                f'test\r\n'
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
                if len(response) > 32768:
                    break

            writer.close()
            await writer.wait_closed()

            header_section, _, body = response.partition(b'\r\n\r\n')
            combined = header_section + b'\n' + body

            import re
            matches = re.findall(self.JWT_REGEX, combined)
            for m in matches:
                parts = m.decode().split('.')
                if len(parts) == 3:
                    return m.decode()

            auth_lines = [l for l in header_section.decode(errors='ignore').split('\r\n')
                          if 'authorization:' in l.lower()]
            for al in auth_lines:
                val = al.split(':', 1)[1].strip()
                if val.startswith('Bearer '):
                    token = val[7:]
                    parts = token.split('.')
                    if len(parts) == 3:
                        return token

            cookie_lines = [l for l in header_section.decode(errors='ignore').split('\r\n')
                            if l.lower().startswith('set-cookie:') and 'jwt' in l.lower() or 'token' in l.lower()]
            for cl in cookie_lines:
                import re as re2
                m2 = re2.search(self.JWT_REGEX, cl.encode())
                if m2:
                    return m2.group().decode()

            return None

        except Exception:
            return None

    async def _try_weak_secret(self, token: str, secret: str) -> bool:
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return False
            header_b64, payload_b64, _ = parts
            header_b64_pad = header_b64 + '=' * (4 - len(header_b64) % 4) if len(header_b64) % 4 else header_b64
            payload_b64_pad = payload_b64 + '=' * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else payload_b64
            header_json = base64.urlsafe_b64decode(header_b64_pad).decode('utf-8')
            header = json.loads(header_json)
            if header.get('alg', '').startswith('HS'):
                import hmac, hashlib
                sig = hmac.new(secret.encode(), f'{header_b64}.{payload_b64}'.encode(), hashlib.sha256).digest()
                sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b'=').decode()
                return sig_b64 == parts[2]
            return False
        except Exception:
            return False
