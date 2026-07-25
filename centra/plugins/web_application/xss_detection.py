"""
Plugin 1044: Cross-Site Scripting (XSS) Detection
====================================================
Injects XSS payloads into page parameters and checks for reflection.
Real CVEs: CVE-2023-43309 (stored XSS), CVE-2023-31434 (reflected XSS)
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class XssDetection(NaslPlugin):
    PLUGIN_ID = 1044
    NAME = 'Cross-Site Scripting (XSS) Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'The web application reflects injected script payloads in HTTP responses. '
        'Reflected XSS allows attackers to execute arbitrary JavaScript in the '
        'context of a victim\'s browser session.'
    )
    SOLUTION = (
        'Implement context-aware output encoding. Use Content Security Policy '
        '(CSP) headers. Validate and sanitize all user input. Use frameworks '
        'with automatic XSS protection.'
    )
    CVE = ['CVE-2023-43309', 'CVE-2023-31434']
    PORTS = [80, 443]

    XSS_PAYLOADS = [
        '<script>alert(1)</script>',
        '"><script>alert(1)</script>',
        '\'><script>alert(1)</script>',
        '<img src=x onerror=alert(1)>',
        '"><img src=x onerror=alert(1)>',
        '<svg onload=alert(1)>',
        'javascript:alert(1)',
    ]
    PROBE_ID = 'centra_xss_scan'

    POST_PATHS = [
        '/comment', '/feedback', '/contact', '/submit',
        '/post', '/review', '/guestbook', '/form',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        probe_value = self.PROBE_ID

        baseline_body = await self._fetch_page(target, port, '/')
        if baseline_body is None:
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description='Could not retrieve page content')]

        params = self._extract_params(baseline_body)

        for payload in self.XSS_PAYLOADS:
            test_value = f'{probe_value}{payload}'
            for param in params[:10]:
                try:
                    reflected = await self._test_reflection(target, port, '/', param, test_value, 'GET')
                    if reflected:
                        return [PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=self.CVSS_SCORE, severity='medium',
                            description=f'XSS reflection detected in parameter "{param}"',
                            solution=self.SOLUTION,
                            evidence=f'Parameter: {param}, Payload: {payload[:50]}, Reflected in GET response body',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2023-43309',
                                'https://www.tenable.com/plugins/nessus/10656',
                            ]
                        )]
                except Exception:
                    pass

            for post_path in self.POST_PATHS:
                try:
                    reflected = await self._test_reflection(target, port, post_path, 'msg', test_value, 'POST')
                    if reflected:
                        return [PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=self.CVSS_SCORE, severity='medium',
                            description=f'XSS reflection via POST on {post_path}',
                            solution=self.SOLUTION,
                            evidence=f'Path: {post_path}, Payload: {payload[:50]}, Reflected in POST response body',
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2023-43309',
                                'https://www.tenable.com/plugins/nessus/10656',
                            ]
                        )]
                except Exception:
                    pass

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No XSS reflection detected'
        )]

    async def _fetch_page(self, target: str, port: int, path: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            req = f'GET {path} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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

            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None

    def _extract_params(self, body: str) -> list[str]:
        params = set()
        patterns = [
            r'name=["\'](\w+)["\']',
            r'id=["\'](\w+)["\']',
            r'\?(\w+)=',
            r'&(\w+)=',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, body):
                params.add(match.group(1))
        return list(params) or ['q', 's', 'search', 'query']

    async def _test_reflection(self, target: str, port: int,
                               path: str, param: str, test_value: str,
                               method: str = 'GET') -> bool:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target, port), timeout=5
        )

        encoded = test_value.replace('<', '%3C').replace('>', '%3E').replace('"', '%22').replace("'", '%27')

        if method == 'POST':
            body = f'{param}={encoded}'
            req = (
                f'POST {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Content-Type: application/x-www-form-urlencoded\r\n'
                f'Content-Length: {len(body)}\r\n'
                f'Connection: close\r\n\r\n{body}'
            )
        else:
            req = f'GET {path}?{param}={encoded} HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'

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

        body = response.split(b'\r\n\r\n', 1)
        body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

        if self.PROBE_ID in body_text:
            for xss_pattern in self.XSS_PAYLOADS:
                clean_pattern = xss_pattern.replace('<', '%3C').replace('>', '%3E')
                if clean_pattern in body_text or xss_pattern in body_text:
                    return True

        return False
