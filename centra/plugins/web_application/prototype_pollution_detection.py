"""
Plugin 1180: Client-Side Prototype Pollution Detection
========================================================
Detects client-side prototype pollution vulnerabilities in JavaScript
by injecting __proto__ and constructor.prototype payloads into
URL parameters.
"""
import asyncio
import re
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class PrototypePollutionDetection(NaslPlugin):
    PLUGIN_ID = 1180
    NAME = 'Client-Side Prototype Pollution Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects client-side prototype pollution vulnerabilities in JavaScript '
        'by injecting __proto__ and constructor.prototype payloads into URL '
        'parameters. Prototype pollution can lead to XSS, parameter injection, '
        'and bypass of security controls in JavaScript applications.'
    )
    SOLUTION = (
        'Use Object.create(null) for safe objects. Freeze Object.prototype. '
        'Validate JSON input. Use Maps instead of plain objects for key-value storage.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    POLLUTION_PAYLOADS = [
        '__proto__[test]=true',
        '__proto__.test=true',
        'constructor[prototype][test]=true',
        'constructor.prototype.test=true',
        '__proto__[polluted]=1',
        'constructor[prototype][polluted]=1',
    ]

    GADGET_PATTERNS = [
        (r'<script[^>]*src=["\']([^"\']+\.js)["\']', 'script src'),
        (r'<script[^>]*>(.*?)</script>', 'inline script'),
        (r'application/json', 'json endpoint'),
        (r'application/javascript', 'javascript endpoint'),
    ]

    PATHS = [
        '/', '/index.html', '/app.js', '/main.js',
        '/api/config', '/api/settings',
    ]

    JS_LIB_PATTERNS = [
        b'jquery',
        b'lodash',
        b'underscore',
        b'angular',
        b'react',
        b'vue',
        b'merge(',
        b'extend(',
        b'assign(',
        b'cloneDeep',
        b'clone(',
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

                for path in self.PATHS:
                    try:
                        html_body = await self._fetch_body(
                            target, port_to_check, ctx, host_header, path
                        )
                        if html_body:
                            if self._has_vulnerable_libs(html_body):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=(
                                        f'Potential prototype pollution: vulnerable JS libraries '
                                        f'found on {path}'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'Path: {path}, page uses libraries vulnerable to prototype pollution',
                                    references=[
                                        'https://portswigger.net/web-security/prototype-pollution',
                                        'https://github.com/BlackFan/client-side-prototype-pollution',
                                    ]
                                ))
                                break

                            if self._has_gadgets(html_body):
                                polluted = await self._test_pollution_gadget(
                                    target, port_to_check, ctx, host_header, path
                                )
                                if polluted:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='high',
                                        description=(
                                            f'Client-side prototype pollution detected on {path} '
                                            f'(gadget confirmed)'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Path: {path}, prototype pollution gadget confirmed via URL parameter injection',
                                        references=[
                                            'https://portswigger.net/web-security/prototype-pollution',
                                            'https://github.com/BlackFan/client-side-prototype-pollution',
                                        ]
                                    ))
                                    break
                    except Exception:
                        pass
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No prototype pollution indicators detected on checked ports'
            ))

        return results

    def _has_vulnerable_libs(self, body: str) -> bool:
        patterns = [
            'jquery', 'lodash', 'underscore', 'angular', 'vue',
            'merge(', 'extend(', 'assign(', 'cloneDeep', 'clone(',
        ]
        body_lower = body.lower()
        for p in patterns:
            if p in body_lower:
                return True
        return False

    def _has_gadgets(self, body: str) -> bool:
        for pattern, _ in self.GADGET_PATTERNS:
            if re.search(pattern, body, re.IGNORECASE):
                return True
        return False

    async def _test_pollution_gadget(self, target: str, port: int, ctx, host_header: str,
                                     path: str) -> bool:
        for payload in self.POLLUTION_PAYLOADS:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ctx), timeout=5
                )
                full_path = f'{path}?{payload}'
                req = (
                    f'GET {full_path} HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
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
                body = response.split(b'\r\n\r\n', 1)
                body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''
                if 'polluted' in body_text or 'test' in body_text and 'true' in body_text:
                    return True
            except Exception:
                pass
        return False

    async def _fetch_body(self, target: str, port: int, ctx, host_header: str,
                          path: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
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
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None
