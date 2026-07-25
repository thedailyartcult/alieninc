"""
Plugin 1042: SQL Injection Detection
======================================
Probes endpoints for SQL injection vulnerabilities by injecting
common SQLi payloads and analyzing response patterns.
Real CVEs: CVE-2023-35829 (SQLi Drupal), CVE-2023-43308 (SQLi Webmin)
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


class SqlInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1042
    NAME = 'SQL Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'The web application may be vulnerable to SQL injection attacks. '
        'SQLi allows an attacker to read, modify, or delete database contents, '
        'potentially gaining full access to the application and underlying system.'
    )
    SOLUTION = (
        'Use parameterized queries / prepared statements. Implement strict input '
        'validation. Use a Web Application Firewall (WAF). Apply least-privilege '
        'database accounts. Regular security testing with Centra or equivalent.'
    )
    CVE = ['CVE-2023-35829', 'CVE-2023-43308']
    PORTS = [80, 443]

    SQLI_PAYLOADS = [
        "' OR '1'='1",
        "' OR 1=1--",
        "1' OR '1'='1",
        "1' OR 1=1--",
        "' UNION SELECT NULL--",
        "' UNION SELECT 1,2,3--",
        "1 AND 1=1",
        "1 AND 1=2",
        "'; DROP TABLE users--",
        "' WAITFOR DELAY '0:0:5'--",
        "1; SELECT SLEEP(5)",
        "'; SELECT pg_sleep(5)--",
    ]

    SQL_ERROR_PATTERNS = [
        b'SQL syntax.*MySQL',
        b'Warning.*mysql_',
        b'MySQLSyntaxErrorException',
        b'Unclosed quotation mark',
        b'ORA-[0-9]{4,5}',
        b'ORA-.*Oracle',
        b'PostgreSQL.*ERROR',
        b'Warning.*\\Wpg_',
        b'Driver.*SQL Server',
        b'Microsoft OLE DB.*SQL',
        b'SQLite/JDBCDriver',
        b'sqlite3.OperationalError',
        b'division by zero',
        b'UNION.*SELECT',
    ]

    PROBE_PATHS = [
        '/',
        '/api/',
        '/search',
        '/products',
        '/api/v1/',
        '/login',
        '/api/login',
    ]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        findings = []

        for path in self.PROBE_PATHS:
            for payload in self.SQLI_PAYLOADS:
                try:
                    result = await self._test_payload(target, port, path, payload)
                    if result:
                        findings.append(result)
                        break
                except Exception:
                    pass
            if findings:
                break

        if findings:
            unique_targets = list(set(f.target for f in findings))
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='critical',
                description=f'SQL injection indicator(s) detected on {len(unique_targets)} endpoint(s)',
                solution=self.SOLUTION,
                evidence='; '.join(f.evidence for f in findings[:3]),
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2023-35829',
                    'https://www.tenable.com/plugins/nessus/10677',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='No SQL injection indicators detected'
        )]

    async def _test_payload(self, target: str, port: int,
                            path: str, payload: str) -> PluginResult | None:
        async def try_method(http_method: str, body_data: str | None = None) -> tuple[bytes, str] | None:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                if http_method == 'POST' and body_data:
                    req = (
                        f'POST {path} HTTP/1.1\r\n'
                        f'Host: {target}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Content-Type: application/x-www-form-urlencoded\r\n'
                        f'Content-Length: {len(body_data)}\r\n'
                        f'Connection: close\r\n\r\n{body_data}'
                    )
                else:
                    encoded = payload.replace(' ', '%20').replace("'", '%27').replace('"', '%22')
                    req = (
                        f'GET {path}?q={encoded}&id={encoded}&search={encoded} HTTP/1.1\r\n'
                        f'Host: {target}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                writer.write(req.encode())
                await writer.drain()
                resp = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    resp += chunk
                    if len(resp) > 16384:
                        break
                writer.close()
                await writer.wait_closed()
                return resp, resp.split(b'\r\n\r\n', 1)[1].decode('utf-8', errors='ignore') if b'\r\n\r\n' in resp else ''
            except Exception:
                return None

        for method, body in [('GET', None), ('POST', f'q={payload}&id={payload}&search={payload}')]:
            result = await try_method(method, body)
            if result is None:
                continue
            response, body_text = result

            for pattern in self.SQL_ERROR_PATTERNS:
                if re.search(pattern, response, re.IGNORECASE):
                    return PluginResult(
                        vulnerable=True, target=target, port=port,
                        cvss_score=self.CVSS_SCORE, severity='critical',
                        description=f'SQL error pattern detected with payload on {path}',
                        solution=self.SOLUTION,
                        evidence=f'Endpoint: {path}, method: {method}, payload: {payload[:40]} matched: {pattern.decode("utf-8", errors="replace")[:60]}',
                    )

            bool_true_len = len(body_text)
            alt_payload = payload.replace("1=1", "1=2") if "1=1" in payload else None
            if alt_payload:
                alt_enc = alt_payload.replace(' ', '%20').replace("'", '%27').replace('"', '%22')
                alt_path = f'{path}?q={alt_enc}&id={alt_enc}&search={alt_enc}'
                try:
                    reader2, writer2 = await asyncio.wait_for(
                        asyncio.open_connection(target, port), timeout=5
                    )
                    alt_req = (
                        f'GET {alt_path} HTTP/1.1\r\n'
                        f'Host: {target}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer2.write(alt_req.encode())
                    await writer2.drain()
                    alt_resp = b''
                    while True:
                        chunk = await asyncio.wait_for(reader2.read(4096), timeout=3)
                        if not chunk:
                            break
                        alt_resp += chunk
                        if len(alt_resp) > 16384:
                            break
                    writer2.close()
                    await writer2.wait_closed()
                    alt_section = alt_resp.split(b'\r\n\r\n', 1)
                    alt_text = alt_section[1].decode('utf-8', errors='ignore') if len(alt_section) > 1 else ''
                    if abs(len(alt_text) - bool_true_len) > 100:
                        return PluginResult(
                            vulnerable=True, target=target, port=port,
                            cvss_score=self.CVSS_SCORE, severity='high',
                            description=f'Boolean-based SQLi indicator on {path}',
                            solution=self.SOLUTION,
                            evidence=f'Endpoint: {path}, response size differential: {abs(len(alt_text) - bool_true_len)} bytes',
                        )
                except Exception:
                    pass

        return None
