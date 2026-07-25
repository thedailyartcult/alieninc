"""
Plugin 1178: OS Command Injection Detection
=============================================
Detects OS command injection vulnerabilities by injecting command
separators (;, |, &&, ||) and ping/sleep commands into common
parameters.
"""
import asyncio
import ssl
import time
import urllib.parse

from plugins import NaslPlugin, PluginResult


class CommandInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1178
    NAME = 'OS Command Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects OS command injection vulnerabilities by injecting command '
        'separators (;, |, &&, ||) and ping/sleep commands into common parameters. '
        'Command injection gives attackers full control over the server OS.'
    )
    SOLUTION = (
        'Avoid calling OS commands from web applications. Use safe API '
        'alternatives. Strictly validate all input. Use allowlists for '
        'allowed commands.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TIME_PAYLOADS = [
        ('; sleep 5', 4),
        ('| sleep 5', 4),
        ('&& sleep 5', 4),
        ('|| sleep 5', 4),
        ('`sleep 5`', 4),
        ('$(sleep 5)', 4),
        ('; ping -c 5 127.0.0.1', 4),
        ('| ping -c 5 127.0.0.1', 4),
        ('& ping -c 5 127.0.0.1 &', 4),
    ]

    OUTPUT_PAYLOADS = [
        '; id',
        '| id',
        '&& id',
        '; whoami',
        '| whoami',
        '&& whoami',
        '; uname -a',
        '| uname -a',
        '; echo CMVudHJh',
        '| echo CMVudHJh',
    ]

    PARAMS = [
        'host', 'ping', 'ip', 'target', 'domain', 'server',
        'url', 'path', 'cmd', 'command', 'exec', 'shell',
    ]

    PATHS = [
        '/', '/api/ping', '/ping', '/api/exec', '/execute',
        '/api', '/cgi-bin', '/tools',
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

                baseline_time = await self._measure_response_time(target, port_to_check, ctx, host_header)

                for payload, threshold in self.TIME_PAYLOADS:
                    for param in self.PARAMS[:5]:
                        for path in self.PATHS[:4]:
                            try:
                                req_time = await self._send_timed_request(
                                    target, port_to_check, ctx, host_header, path, param, payload
                                )
                                if req_time and req_time > baseline_time + threshold:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=(
                                            f'OS command injection detected via param "{param}" '
                                            f'on {path} (time delay: {req_time:.1f}s)'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, response time: {req_time:.2f}s, baseline: {baseline_time:.2f}s',
                                        references=[
                                            'https://owasp.org/www-community/attacks/Command_Injection',
                                            'https://portswigger.net/web-security/os-command-injection',
                                        ]
                                    ))
                                    break
                            except Exception:
                                pass
                        if results:
                            break
                    if results:
                        break

                if not results:
                    for payload in self.OUTPUT_PAYLOADS:
                        for param in self.PARAMS[:5]:
                            for path in self.PATHS[:4]:
                                try:
                                    body_text = await self._fetch_body(
                                        target, port_to_check, ctx, host_header, path, param, payload
                                    )
                                    if body_text:
                                        indicator = self._check_output_indicator(body_text)
                                        if indicator:
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='critical',
                                                description=(
                                                    f'OS command injection detected via param "{param}" '
                                                    f'on {path} (command output reflected)'
                                                ),
                                                solution=self.SOLUTION,
                                                evidence=f'Payload: {payload}, indicator: {indicator} found in response',
                                                references=[
                                                    'https://owasp.org/www-community/attacks/Command_Injection',
                                                    'https://portswigger.net/web-security/os-command-injection',
                                                ]
                                            ))
                                            break
                                except Exception:
                                    pass
                            if results:
                                break
                        if results:
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No OS command injection indicators detected on checked ports'
            ))

        return results

    def _check_output_indicator(self, body: str) -> str | None:
        indicators = ['uid=', 'gid=', 'root:', 'CMVudHJh', 'Linux', 'windows', 'nt authority']
        for ind in indicators:
            if ind in body:
                return ind
        return None

    async def _measure_response_time(self, target: str, port: int, ctx, host_header: str) -> float:
        times = []
        for _ in range(2):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ctx), timeout=5
                )
                req = (
                    f'GET / HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Connection: close\r\n\r\n'
                )
                start = time.monotonic()
                writer.write(req.encode())
                await writer.drain()
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                end = time.monotonic()
                writer.close()
                await writer.wait_closed()
                times.append(end - start)
            except Exception:
                pass
        return sum(times) / len(times) if times else 0.5

    async def _send_timed_request(self, target: str, port: int, ctx, host_header: str,
                                  path: str, param: str, payload: str) -> float | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=10
            )
            encoded = urllib.parse.quote(payload)
            req = (
                f'GET {path}?{param}={encoded} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n\r\n'
            )
            start = time.monotonic()
            writer.write(req.encode())
            await writer.drain()
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
                if not chunk:
                    break
            end = time.monotonic()
            writer.close()
            await writer.wait_closed()
            return end - start
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
            return None

    async def _fetch_body(self, target: str, port: int, ctx, host_header: str,
                          path: str, param: str, payload: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            encoded = urllib.parse.quote(payload)
            req = (
                f'GET {path}?{param}={encoded} HTTP/1.1\r\n'
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
                if len(response) > 16384:
                    break
            writer.close()
            await writer.wait_closed()
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None
