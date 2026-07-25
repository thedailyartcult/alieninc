"""
Plugin 1127: API Key Exposure in Client-Side Code
====================================================
Detects API keys exposed in client-side JavaScript and HTML responses.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class ApiKeyExposureDetection(NaslPlugin):
    PLUGIN_ID = 1127
    NAME = 'API Key Exposure in Client-Side Code'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects potential API key and secret exposure by analyzing response '
        'bodies for patterns matching common API key formats (AWS keys, Google '
        'API keys, Stripe keys, GitHub tokens, Slack tokens, generic Bearer '
        'tokens). Exposed keys can lead to account compromise and service abuse.'
    )
    SOLUTION = (
        'Never embed API keys in client-side code. Use proxy/wrapper APIs that '
        'authenticate server-side. Rotate any exposed keys immediately.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    API_KEY_PATTERNS = [
        (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
        (r'(?i)google.*api.*key[=:]["\' ]?[A-Za-z0-9_-]{30,50}', 'Google API Key'),
        (r'sk_live_[0-9a-zA-Z]{24,}', 'Stripe Live Secret Key'),
        (r'pk_live_[0-9a-zA-Z]{24,}', 'Stripe Live Publishable Key'),
        (r'ghp_[0-9a-zA-Z]{36,}', 'GitHub Personal Access Token'),
        (r'gho_[0-9a-zA-Z]{36,}', 'GitHub OAuth Access Token'),
        (r'xox[baprs]-[0-9a-zA-Z-]{24,}', 'Slack Token'),
        (r'(?i)api[_-]?key[:=]["\' ][A-Za-z0-9_\-]{16,64}', 'Generic API Key'),
        (r'(?i)secret[:=]["\' ][A-Za-z0-9_\-/\+=]{16,64}', 'Generic Secret'),
        (r'Bearer [A-Za-z0-9_\-\.]{20,200}', 'Bearer Token'),
        (r'(?i)aws[_-]?secret[_-]?access[_-]?key[=:]["\' ]?[A-Za-z0-9/+=]{40}', 'AWS Secret Key'),
    ]

    JS_PATHS = [
        '/', '/app.js', '/main.js', '/bundle.js', '/vendor.js',
        '/assets/js/', '/static/js/', '/api.js', '/config.js',
    ]

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

                found_keys = []

                for path in self.JS_PATHS:
                    body = await self._fetch_body(target, p, path, ctx)
                    if body:
                        for pattern, key_type in self.API_KEY_PATTERNS:
                            matches = re.findall(pattern, body.decode(errors='ignore'))
                            for m in matches[:3]:
                                truncated = m[:20] + '...' if len(m) > 20 else m
                                found_keys.append(f'{key_type}: {truncated}')
                                if len(found_keys) >= 10:
                                    break
                        if len(found_keys) >= 10:
                            break

                if found_keys:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity='high',
                        description=f'Potential API key exposure: {len(found_keys)} pattern(s) matched',
                        solution=self.SOLUTION,
                        evidence='; '.join(found_keys[:10]),
                        references=[
                            'https://owasp.org/www-community/attacks/Credential_stuffing',
                            'https://www.tenable.com/plugins/nessus/10428',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        description='No API key patterns detected in client-side responses'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    description=f'Port {p} not reachable'
                ))

        return results

    async def _fetch_body(self, target: str, port: int, path: str, ctx: ssl.SSLContext | None) -> bytes | None:
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
                f'Accept: */*\r\n'
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
                if len(response) > 65536:
                    break

            writer.close()
            await writer.wait_closed()

            status = response.split(b'\r\n')[0].decode(errors='ignore')
            if '200' not in status:
                return None

            _, _, body = response.partition(b'\r\n\r\n')
            return body

        except Exception:
            return None
