"""
Plugin 1020: HTTP Method Override Bypass
==========================================
Tests whether bot detection can be circumvented by sending a GET
request with HTTP method override headers that cause the server
to treat it as a different HTTP method (PUT, DELETE, PATCH). Many
frameworks (Symfony, Laravel, Rails, Express) support method
override via X-HTTP-Method, X-HTTP-Method-Override, or
X-Method-Override headers.

Real references:
  CWE-693   — Protection Mechanism Failure
  OWASP WSTG-CONF-06 — Test HTTP Methods
  Nessus Plugin 43160 — HTTP Method Override Detection
"""
import asyncio, re

from plugins import NaslPlugin, PluginResult


class HttpMethodOverride(NaslPlugin):
    PLUGIN_ID = 1020
    NAME = 'HTTP Method Override Bypass'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 6.5
    DESCRIPTION = (
        'Tests whether HTTP method override headers (X-HTTP-Method, '
        'X-HTTP-Method-Override, X-Method-Override) can be used to '
        'bypass bot detection. If a bot sends GET with one of these '
        'headers set to DELETE/PUT/PATCH, the server may process it '
        'as a different method, potentially bypassing UA-based checks '
        'that only apply to GET.'
    )
    SOLUTION = (
        '1. Strip X-HTTP-Method, X-HTTP-Method-Override, and '
        'X-Method-Override headers from bot requests before processing. '
        '2. Apply bot detection uniformly to all HTTP methods, not just '
        'GET. 3. Return 405 for methods not explicitly supported.'
    )
    CVE = ['CVE-2021-42013']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    OVERRIDE_HEADERS = [
        'X-HTTP-Method',
        'X-HTTP-Method-Override',
        'X-Method-Override',
    ]

    async def _send_raw(self, target, port, method, path, ua, extra_headers=None, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {}, '')

        try:
            req = (
                f'{method} {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: {ua}\r\n'
            )
            if extra_headers:
                for k, v in extra_headers.items():
                    req += f'{k}: {v}\r\n'
            req += f'Connection: close\r\n\r\n'

            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                if not chunk:
                    break
                response += chunk
                if len(response) > 131072:
                    break
        except Exception:
            return ('TIMEOUT', {}, '')
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        parts = response.split(b'\r\n\r\n', 1)
        header_section = parts[0].decode('utf-8', errors='ignore')
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        lines = header_section.split('\r\n')
        status_line = lines[0] if lines else ''
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        return (status_line, headers, body)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUMAN = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        marker = 'Private operating group'

        # Baseline: GET with bot UA (should be sanitized)
        s_base, h_base, body_base = await self._send_raw(target, port, 'GET', '/', BOT)
        baseline_sanitized = marker in body_base
        baseline_len = len(body_base)

        findings = []
        evidence_lines = []

        for ov_header in self.OVERRIDE_HEADERS:
            for override_method in ['DELETE', 'PUT', 'PATCH']:
                s, h, body = await self._send_raw(
                    target, port, 'GET', '/', BOT,
                    extra_headers={ov_header: override_method}, timeout=8
                )
                await asyncio.sleep(0.05)

                is_sanitized = marker in body
                body_len = len(body) if body else 0
                status_ok = '200' in s

                info = (
                    f'{ov_header}: {override_method} → '
                    f'status={"200" if status_ok else s[:30]} '
                    f'len={body_len} sanitized={is_sanitized}'
                )
                evidence_lines.append(info)

                # Check for bypass: different content from baseline
                if status_ok:
                    if not is_sanitized and baseline_sanitized:
                        findings.append((
                            'high',
                            f'{ov_header}: {override_method} — bypasses sanitization '
                            f'(got unsanitized {body_len}B, baseline is sanitized '
                            f'{baseline_len}B)'
                        ))
                    elif is_sanitized and body_len != baseline_len:
                        findings.append((
                            'medium',
                            f'{ov_header}: {override_method} — different response size '
                            f'({body_len}B vs baseline {baseline_len}B). Server may '
                            f'process override differently.'
                        ))
                    elif not is_sanitized and not baseline_sanitized:
                        findings.append((
                            'low',
                            f'{ov_header}: {override_method} — unsanitized (but '
                            f'baseline also unsanitized, bot detection may be off)'
                        ))

        if findings:
            max_sev = 'info'
            sev_order = {'high': 4, 'medium': 3, 'low': 2}
            for sev, _ in findings:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev
            cvss_map = {'high': 6.5, 'medium': 4.3, 'low': 2.5}
            cvss = cvss_map.get(max_sev, 1.0)

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description=f'Method override bypass: {findings[0][1][:150]}',
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://cwe.mitre.org/data/definitions/693.html',
                    'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/06-Test_HTTP_Methods',
                ],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description='Method override headers do not bypass bot detection. Server ignores or sanitizes override attempts.',
                solution='No action required.',
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))

        return results
