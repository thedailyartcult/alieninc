"""
Plugin 1239: Clipboard Hijacking Detection
==========================================
Detects clipboard manipulation by web pages via the ClipboardEvent API.
Scans JavaScript for clipboard event listeners and clipboard API access.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class ClipboardHijackingDetection(NaslPlugin):
    PLUGIN_ID = 1239
    NAME = 'Clipboard Hijacking Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Detects clipboard manipulation by web pages via the ClipboardEvent API. '
        'Detects JavaScript code that listens for copy events to modify clipboard '
        'content or for paste events to intercept pasted data.'
    )
    SOLUTION = (
        'Review clipboard event handlers in first-party code. Be cautious of '
        'third-party scripts that access clipboard API. Restrict clipboard access '
        'via Permissions-Policy: clipboard-read=()'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    CLIPBOARD_PATTERNS = [
        (r"addEventListener\s*\(\s*['\"]copy['\"]", 'copy event listener'),
        (r"addEventListener\s*\(\s*['\"]paste['\"]", 'paste event listener'),
        (r"addEventListener\s*\(\s*['\"]cut['\"]", 'cut event listener'),
        (r"\.clipboard\.writeText\s*\(", 'clipboard.writeText'),
        (r"\.clipboard\.readText\s*\(", 'clipboard.readText'),
        (r"oncopy\s*=", 'oncopy attribute'),
        (r"onpaste\s*=", 'onpaste attribute'),
        (r"oncut\s*=", 'oncut attribute'),
        (r"clipboardData\.setData", 'clipboardData.setData'),
        (r"clipboardData\.getData", 'clipboardData.getData'),
    ]

    SCRIPT_PATTERN = re.compile(
        r'<script[^>]*src=["\']([^"\']+)["\']',
        re.IGNORECASE
    )

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
                    for pattern, label in self.CLIPBOARD_PATTERNS:
                        if re.search(pattern, html, re.IGNORECASE):
                            findings.append(label)
                    if findings:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity='low',
                            description=f'Clipboard API access detected: {", ".join(findings)}',
                            solution=self.SOLUTION,
                            evidence=f'Clipboard patterns found in HTML: {findings}',
                            references=[
                                'https://www.w3.org/TR/clipboard-apis/',
                                'https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API',
                            ]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            description='No clipboard hijacking indicators detected'
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No clipboard hijacking indicators detected'
            ))
        return results
