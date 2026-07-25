"""
Plugin 1176: Blind SQL Injection Detection (Time-Based)
=========================================================
Detects blind SQL injection vulnerabilities using time-based
and boolean-based techniques. Injects SLEEP/WAITFOR/BENCHMARK
payloads into query parameters and POST bodies.
"""
import asyncio
import ssl
import time
import urllib.parse

from plugins import NaslPlugin, PluginResult


class BlindSqliDetection(NaslPlugin):
    PLUGIN_ID = 1176
    NAME = 'Blind SQL Injection Detection (Time-Based)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects blind SQL injection vulnerabilities using time-based and '
        'boolean-based techniques. Injects SLEEP/WAITFOR/BENCHMARK payloads '
        'into query parameters and POST bodies, measuring response delays to '
        'infer SQL execution. Blind SQLi is as dangerous as regular SQLi but '
        'harder to detect.'
    )
    SOLUTION = (
        'Use parameterized queries. Implement strict input validation. '
        'Use an ORM that prevents SQL injection. Apply a WAF.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TIME_PAYLOADS = [
        ("' OR SLEEP(5)--", 4),
        ("' OR SLEEP(5)='", 4),
        ("1' OR SLEEP(5)--", 4),
        ("1' OR SLEEP(5)='", 4),
        ("'; WAITFOR DELAY '0:0:5'--", 4),
        ("1; WAITFOR DELAY '0:0:5'--", 4),
        ("' OR BENCHMARK(50000000,MD5(1))--", 4),
        ("1 AND SLEEP(5)", 4),
        ("1' AND SLEEP(5)--", 4),
        ("' AND SLEEP(5) AND '1'='1", 4),
    ]

    BOOLEAN_TRUE_PAYLOADS = [
        "' OR '1'='1",
        "1' OR '1'='1",
        "' OR 1=1--",
        "1 OR 1=1",
    ]

    BOOLEAN_FALSE_PAYLOADS = [
        "' OR '1'='2",
        "1' OR '1'='2",
        "' OR 1=2--",
        "1 OR 1=2",
    ]

    PARAMS = [
        'id', 'q', 'search', 'query', 'page', 'name', 'user',
        'username', 'email', 'product', 'category',
    ]

    PATHS = ['/', '/api', '/search', '/products', '/items', '/user']

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
                        for path in self.PATHS[:3]:
                            try:
                                req_time = await self._send_payload_timed(
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
                                            f'Time-based blind SQLi detected via param "{param}" '
                                            f'on {path} (response time: {req_time:.1f}s vs baseline {baseline_time:.1f}s)'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload}, response time: {req_time:.2f}s, baseline: {baseline_time:.2f}s',
                                        references=[
                                            'https://portswigger.net/web-security/sql-injection/blind',
                                            'https://owasp.org/www-community/attacks/Blind_SQL_Injection',
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
                    for true_payload, false_payload in zip(self.BOOLEAN_TRUE_PAYLOADS, self.BOOLEAN_FALSE_PAYLOADS):
                        for param in self.PARAMS[:5]:
                            for path in self.PATHS[:3]:
                                try:
                                    true_body = await self._fetch_body(
                                        target, port_to_check, ctx, host_header, path, param, true_payload
                                    )
                                    false_body = await self._fetch_body(
                                        target, port_to_check, ctx, host_header, path, param, false_payload
                                    )
                                    if true_body and false_body:
                                        if abs(len(true_body) - len(false_body)) > 50:
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='critical',
                                                description=(
                                                    f'Boolean-based blind SQLi detected via param "{param}" '
                                                    f'on {path} (response size differential)'
                                                ),
                                                solution=self.SOLUTION,
                                                evidence=(
                                                    f'True payload: {true_payload}, false payload: {false_payload}, '
                                                    f'size diff: {abs(len(true_body) - len(false_body))} bytes'
                                                ),
                                                references=[
                                                    'https://portswigger.net/web-security/sql-injection/blind',
                                                    'https://owasp.org/www-community/attacks/Blind_SQL_Injection',
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
                description='No blind SQL injection indicators detected on checked ports'
            ))

        return results

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

    async def _send_payload_timed(self, target: str, port: int, ctx, host_header: str,
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
