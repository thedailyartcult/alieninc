"""
Plugin 1123: Content Security Policy Evaluation
=================================================
Evaluates the Content-Security-Policy header for common misconfigurations
including unsafe-inline, unsafe-eval, wildcard sources (*), and missing
directives.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CspEvaluation(NaslPlugin):
    PLUGIN_ID = 1123
    NAME = 'Content Security Policy Evaluation'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Evaluates the Content-Security-Policy (CSP) header for common '
        'misconfigurations including unsafe-inline, unsafe-eval, wildcard '
        'sources (*), and missing directives. A weak CSP exposes users to XSS '
        'attacks by failing to restrict script/style sources.'
    )
    SOLUTION = (
        'Implement a strict CSP without unsafe-* directives. Use nonces or '
        'hashes for inline scripts. Avoid wildcard sources. Include base-uri '
        'and form-action directives.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    UNSAFE_PATTERNS = [
        "'unsafe-inline'",
        "'unsafe-eval'",
        '*',
        'http://*',
        'https://*',
    ]

    RECOMMENDED_DIRECTIVES = [
        'default-src', 'script-src', 'style-src', 'img-src',
        'connect-src', 'font-src', 'object-src', 'frame-src',
        'base-uri', 'form-action',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                    timeout=5
                )

                req = (
                    f'GET / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Connection: close\r\n\r\n'
                )
                writer.write(req.encode())
                await writer.drain()

                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 16384:
                            break
                except asyncio.TimeoutError:
                    pass

                writer.close()
                await writer.wait_closed()

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                headers = {}
                for line in header_section.split('\r\n')[1:]:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        headers[key.strip().lower()] = val.strip()

                csp = headers.get('content-security-policy', '')
                csp_report = headers.get('content-security-policy-report-only', '')

                findings = []

                if not csp and not csp_report:
                    findings.append('No CSP header found')
                else:
                    csp_value = csp or csp_report
                    directives = {}
                    for part in csp_value.split(';'):
                        part = part.strip()
                        if part:
                            tokens = part.split()
                            if tokens:
                                directives[tokens[0]] = tokens[1:] if len(tokens) > 1 else []

                    found_directives = set(directives.keys())
                    missing = [d for d in self.RECOMMENDED_DIRECTIVES if d not in found_directives]
                    if missing:
                        findings.append(f'Missing directives: {", ".join(missing)}')

                    for directive, sources in directives.items():
                        for src in sources:
                            for unsafe in self.UNSAFE_PATTERNS:
                                if unsafe in src:
                                    findings.append(f'{directive} contains {unsafe}')

                if findings:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='medium',
                        description='CSP misconfiguration(s) detected',
                        solution=self.SOLUTION,
                        evidence='; '.join(findings[:5]),
                        references=[
                            'https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP',
                            'https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html',
                        ]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='CSP header appears properly configured'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='Could not evaluate CSP on checked ports'
            ))

        return results
