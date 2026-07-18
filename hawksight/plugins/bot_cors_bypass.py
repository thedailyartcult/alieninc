"""
Plugin 1022: CORS Preflight Bot Bypass
========================================
Tests whether CORS preflight (OPTIONS) requests with bot User-Agent
strings bypass bot detection and return unrestricted CORS headers
(Access-Control-Allow-Origin: *, Allow: full list of methods).
If preflight responses differ between bot and human UAs, attackers
can use this to fingerprint the detection system.

Real references:
  CWE-942   — Permissive Cross-domain Policy with Untrusted Domains
  OWASP WSTG-CLIENT-07 — Testing Cross Origin Resource Sharing
  Nessus Plugin 98051 — CORS Allow-Origin Wildcard Detection
"""
import asyncio, re

from plugins import NaslPlugin, PluginResult


class CorsPreflightBotBypass(NaslPlugin):
    PLUGIN_ID = 1022
    NAME = 'CORS Preflight Bot Bypass'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.0
    DESCRIPTION = (
        'Sends OPTIONS (preflight) requests with bot and human User-Agent '
        'strings to compare CORS response headers. If the server returns '
        'different Access-Control-Allow-* headers for bots vs humans, '
        'or returns "Access-Control-Allow-Origin: *" to bot requests, '
        'attackers can enumerate allowed methods and origins for '
        'cross-origin attacks from bot-identifying UAs.'
    )
    SOLUTION = (
        '1. Apply bot detection to OPTIONS requests the same as GET. '
        '2. Do not return CORS headers for bot User-Agents. '
        '3. Never use Access-Control-Allow-Origin: * in production. '
        '4. Strip Allow header from bot responses to avoid method enumeration.'
    )
    CVE = ['CVE-2021-42013']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _send_raw(self, target, port, method, path, ua, extra_headers=None, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {})

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
                if len(response) > 65536:
                    break
        except Exception:
            return ('TIMEOUT', {})
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        header_section = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
        lines = header_section.split('\r\n')
        status_line = lines[0] if lines else ''
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        return (status_line, headers)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        origins = ['https://evil.com', 'null', 'http://localhost:3000']
        methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']

        findings = []
        evidence_lines = []

        for origin in origins:
            for ua_label, ua in [('bot', BOT), ('human', HUM)]:
                s, h = await self._send_raw(
                    target, port, 'OPTIONS', '/', ua,
                    extra_headers={
                        'Origin': origin,
                        'Access-Control-Request-Method': 'GET',
                    },
                    timeout=8
                )
                await asyncio.sleep(0.05)

                allow_origin = h.get('access-control-allow-origin', '').strip()
                allow_methods = h.get('access-control-allow-methods', '').strip()
                allow_headers = h.get('access-control-allow-headers', '').strip()
                allow_creds = h.get('access-control-allow-credentials', '').strip()

                info = (
                    f'{ua_label} OPTIONS origin={origin} → '
                    f'ACAO={allow_origin or "none"} '
                    f'ACAM={allow_methods or "none"} '
                    f'ACAC={allow_creds or "none"}'
                )
                evidence_lines.append(info)

                # Check for wildcard origin
                if allow_origin == '*':
                    findings.append((
                        'high',
                        f'{ua_label}: ACAO wildcard (*) for origin={origin}. '
                        f'Any domain can make cross-origin requests.'
                    ))
                # Check for reflected origin
                elif allow_origin == origin:
                    findings.append((
                        'medium',
                        f'{ua_label}: Origin reflected ({origin}). '
                        f'Server trusts arbitrary origins.'
                    ))
                # Check if Allow header discloses methods
                allow = h.get('allow', '')
                if allow and len(allow.split(',')) > 2:
                    findings.append((
                        'low',
                        f'{ua_label}: Allow header discloses '
                        f'{len(allow.split(","))} methods: {allow}'
                    ))
                # Check for credentials allowed
                if allow_creds.lower() == 'true' and allow_origin != '*':
                    findings.append((
                        'medium',
                        f'{ua_label}: Access-Control-Allow-Credentials: true '
                        f'with reflected origin ({origin})'
                    ))

        if findings:
            max_sev = 'info'
            sev_order = {'high': 4, 'medium': 3, 'low': 2}
            for sev, _ in findings:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev
            cvss_map = {'high': 5.3, 'medium': 3.7, 'low': 2.1}
            cvss = cvss_map.get(max_sev, 1.0)

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description=f'CORS preflight info leak: {findings[0][1][:150]}',
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://cwe.mitre.org/data/definitions/942.html',
                    'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/11-Client-side_Testing/07-Testing_Cross_Origin_Resource_Sharing',
                ],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description='CORS preflight responses consistent. No wildcard origins or reflected origins detected.',
                solution='No action required.',
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))

        return results
