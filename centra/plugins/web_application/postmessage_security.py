import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult


class PostMessageSecurity(NaslPlugin):
    PLUGIN_ID = 1190
    NAME = 'PostMessage Security Assessment'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Assesses window.postMessage usage for security vulnerabilities including missing origin validation, wildcard target origins, and sensitive data exposure via message passing. Unrestricted postMessage can lead to data theft and XSS via parent-origin attacks.'
    SOLUTION = 'Always validate the origin of incoming messages. Specify exact target origin instead of *. Use addEventListener for message handling. Validate message data structure before processing.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            js_sources = []
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()
                response = b''
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk: break
                        response += chunk
                        if len(response) > 32768: break
                except asyncio.TimeoutError:
                    pass
                writer.close()
                await writer.wait_closed()

                if response:
                    body = response.split(b'\r\n\r\n', 1)
                    if len(body) > 1:
                        html = body[1].decode('utf-8', errors='ignore')
                        inline_scripts = re.findall(r'<script[^>]*>([^<]+)</script>', html, re.IGNORECASE | re.DOTALL)
                        js_sources.extend(inline_scripts)
                        script_srcs = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                        for src in script_srcs[:5]:
                            try:
                                js_scheme = 'https' if port_to_check in (443, 8443) else 'http'
                                js_ctx = None
                                if js_scheme == 'https':
                                    js_ctx = ssl.create_default_context()
                                    js_ctx.check_hostname = False
                                    js_ctx.verify_mode = ssl.CERT_NONE
                                js_reader, js_writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=js_ctx), timeout=5)
                                js_req = f'GET {src} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                                js_writer.write(js_req.encode())
                                await js_writer.drain()
                                js_response = b''
                                try:
                                    while True:
                                        chunk = await asyncio.wait_for(js_reader.read(4096), timeout=3)
                                        if not chunk: break
                                        js_response += chunk
                                        if len(js_response) > 32768: break
                                except asyncio.TimeoutError:
                                    pass
                                js_writer.close()
                                await js_writer.wait_closed()
                                if js_response:
                                    js_body = js_response.split(b'\r\n\r\n', 1)
                                    if len(js_body) > 1:
                                        js_sources.append(js_body[1].decode('utf-8', errors='ignore'))
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass

                        findings = []
                        for js in js_sources:
                            post_message_calls = re.findall(r'\.postMessage\s*\(([^)]+)\)', js)
                            for call in post_message_calls:
                                if "'*'" in call or '"*"' in call:
                                    findings.append(f'Wildcard targetOrigin in postMessage: .postMessage({call})')
                            message_listeners = re.findall(r'addEventListener\s*\(\s*[\'"]message[\'"]\s*,\s*(\w+)', js)
                            for listener in message_listeners:
                                func_pattern = re.compile(
                                    r'(?:function\s+' + re.escape(listener) + r'|' + re.escape(listener) + r'\s*=\s*function|' + re.escape(listener) + r'\s*[:=]\s*(?:async\s+)?\([^)]*\))\s*\{([^}]+)\}',
                                    re.DOTALL
                                )
                                func_match = func_pattern.search(js)
                                if func_match:
                                    func_body = func_match.group(1) if func_match.lastindex else ''
                                    if 'event.origin' not in func_body and 'e.origin' not in func_body:
                                        findings.append(f'Message listener "{listener}" missing origin validation')
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'PostMessage vulnerabilities: {len(findings)} issues',
                                solution=self.SOLUTION,
                                evidence='PostMessage issues:\n' + '\n'.join(findings)
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=port_to_check,
                                description='No issues detected'
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
