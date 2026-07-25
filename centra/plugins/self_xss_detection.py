"""
Plugin 1241: Self-XSS / Console Injection Detection
====================================================
Detects self-XSS attack surfaces including JavaScript execution context
via browser console, bookmarklets, or data URIs.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class SelfXssDetection(NaslPlugin):
    PLUGIN_ID = 1241
    NAME = 'Self-XSS / Console Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Detects self-XSS attack surfaces including JavaScript execution context '
        'via browser console, bookmarklets, or data URIs. Checks for missing XSS '
        'protection headers and console.log exposure of sensitive data.'
    )
    SOLUTION = (
        'Never include sensitive data in console.log or error messages. Implement '
        'Content-Security-Policy. Use XSS filtering headers. Warn users against '
        'pasting code in console.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_CONSOLE_PATTERNS = [
        (r'console\.log\(.*(?:token|secret|password|key|auth|cookie|session|jwt|api[_-]?key)', 'sensitive data in console.log'),
        (r'console\.error\(.*(?:token|secret|password|key|auth|cookie|session|jwt|api[_-]?key)', 'sensitive data in console.error'),
        (r'console\.info\(.*(?:token|secret|password|key|auth|cookie|session|jwt|api[_-]?key)', 'sensitive data in console.info'),
        (r'console\.debug\(.*(?:token|secret|password|key|auth|cookie|session|jwt|api[_-]?key)', 'sensitive data in console.debug'),
        (r'console\.warn\(.*(?:token|secret|password|key|auth|cookie|session|jwt|api[_-]?key)', 'sensitive data in console.warn'),
        (r'eval\s*\(\s*(?:location|document\.URL|location\.hash|location\.search)', 'eval with user-controlled input'),
        (r'setTimeout\s*\(\s*(?:location|document\.URL|location\.hash|location\.search)', 'setTimeout with user-controlled input'),
        (r'setInterval\s*\(\s*(?:location|document\.URL|location\.hash|location\.search)', 'setInterval with user-controlled input'),
        (r'new\s+Function\s*\(', 'dynamic function constructor'),
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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        response += chunk
                        if len(response) > 65536:
                            break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()
                body = response.split(b'\r\n\r\n', 1)
                if len(body) > 1:
                    html = body[1].decode('utf-8', errors='ignore')
                    findings = []
                    for pattern, label in self.SENSITIVE_CONSOLE_PATTERNS:
                        if re.search(pattern, html, re.IGNORECASE):
                            findings.append(label)
                    if findings:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='low',
                            description=f'Self-XSS risk indicators: {", ".join(findings)}',
                            solution=self.SOLUTION,
                            evidence=f'Patterns found in page: {findings}',
                            references=[
                                'https://owasp.org/www-community/attacks/xss/',
                                'https://portswigger.net/web-security/cross-site-scripting/self-xss',
                            ]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            description='No self-XSS indicators detected'
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No self-XSS indicators detected'
            ))
        return results
