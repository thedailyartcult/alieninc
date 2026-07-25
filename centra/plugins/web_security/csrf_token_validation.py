"""
Plugin 1045: CSRF Token Validation
=====================================
Checks that HTML forms include anti-CSRF tokens.
Real CVEs: CVE-2024-49672 (CSRF to XSS), CVE-2022-22834 (Django timing)
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class CsrfTokenValidation(NaslPlugin):
    PLUGIN_ID = 1045
    NAME = 'CSRF Token Validation'
    FAMILY = 'Web Security'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'HTML forms on the web application lack anti-CSRF tokens. '
        'Cross-Site Request Forgery (CSRF) allows attackers to execute '
        'unauthorized actions on behalf of authenticated users.'
    )
    SOLUTION = (
        'Implement anti-CSRF tokens for all state-changing forms. Use '
        'SameSite cookies (Strict/Lax). Validate Origin and Referer headers. '
        'Use frameworks with built-in CSRF protection.'
    )
    CVE = ['CVE-2022-22834', 'CVE-2024-49672']
    PORTS = [80, 443]

    CSRF_TOKEN_PATTERNS = [
        r'csrf',
        r'csrf_token',
        r'csrfmiddlewaretoken',
        r'__csrf',
        r'xsrf',
        r'xsrf-token',
        r'csrf-token',
        r'csrfparam',
        r'nonce',
        r'authenticity_token',
        r'_token',
        r'__RequestVerificationToken',
        r'form_token',
        r'security_token',
    ]

    SKIP_METHODS = {'get', 'GET'}

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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

            body = response.split(b'\r\n\r\n', 1)
            body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

            forms = re.findall(r'<form[^>]*>', body_text, re.IGNORECASE)

            if not forms:
                return [PluginResult(
                    vulnerable=False, target=target, port=port,
                    severity='info',
                    description='No HTML forms found on the page'
                )]

            forms_with_tokens = 0
            forms_without_tokens = []
            form_count = 0

            for match in re.finditer(r'<form[^>]*>(.*?)</form>', body_text, re.IGNORECASE | re.DOTALL):
                form_tag = match.group(0)
                form_html = match.group(1)
                form_count += 1

                method_match = re.search(r'method\s*=\s*["\'](\w+)["\']', form_tag, re.IGNORECASE)
                method = method_match.group(1).upper() if method_match else 'GET'

                if method in self.SKIP_METHODS:
                    forms_with_tokens += 1
                    continue

                has_token = any(
                    re.search(rf'(?:name|id)\s*=\s*["\'][^"\']*{pattern}[^"\']*["\']',
                              form_html + form_tag, re.IGNORECASE)
                    for pattern in self.CSRF_TOKEN_PATTERNS
                )

                if has_token:
                    forms_with_tokens += 1
                else:
                    action_match = re.search(r'action\s*=\s*["\']([^"\']*)["\']', form_tag, re.IGNORECASE)
                    action = action_match.group(1) if action_match else '(no action)'
                    forms_without_tokens.append(action)

            if forms_without_tokens:
                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='medium',
                    description=f'{len(forms_without_tokens)} form(s) without CSRF tokens ({forms_with_tokens}/{form_count} protected)',
                    solution=self.SOLUTION,
                    evidence=f'Forms without CSRF tokens: {", ".join(forms_without_tokens[:5])}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-44487',
                        'https://www.tenable.com/plugins/nessus/143906',
                    ]
                )]

            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'All {forms_with_tokens} form(s) include CSRF protection'
            )]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Port {port} not reachable'
            )]
