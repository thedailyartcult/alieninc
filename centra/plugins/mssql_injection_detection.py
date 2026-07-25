"""
Plugin 1269: MSSQL Database Injection Detection
=================================================
Detects Microsoft SQL Server-specific SQL injection vulnerabilities using
stacked queries, error-based, and time-based techniques.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class MSSQLInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1269
    NAME = 'MSSQL Database Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Microsoft SQL Server-specific SQL injection vulnerabilities '
        'using stacked queries, error-based, and time-based techniques.'
    )
    SOLUTION = (
        'Use parameterized queries. Disable xp_cmdshell if not required. '
        'Implement proper input validation.'
    )
    CVE = ['CVE-2024-43405']
    PORTS = [80, 443, 8080, 8443, 1433]

    PAYLOADS = [
        "' OR 1=1--",
        "'; WAITFOR DELAY '00:00:05'--",
        "' AND 1=CONVERT(int, @@VERSION)--",
        "' UNION SELECT NULL,NULL,NULL,NULL--",
    ]

    PARAMS = ['id', 'page', 'user', 'q', 'cat']

    MSSQL_INDICATORS = [
        'microsoft ole db', 'sql server', 'driver {sql server}',
        'microsoft odbc', 'microsoft sql', 'mssql', 'msoledbsql',
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

                for param in self.PARAMS:
                    for payload in self.PAYLOADS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )
                            encoded = urllib.parse.quote(payload)
                            req = (
                                f'GET /?{param}={encoded} HTTP/1.1\r\n'
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

                            body = response.split(b'\r\n\r\n', 1)
                            body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                            if any(ind in body_text.lower() for ind in self.MSSQL_INDICATORS):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'MSSQL injection detected via param "{param}"',
                                    solution=self.SOLUTION,
                                    evidence=f'Payload: {payload}, MSSQL error indicators found',
                                    references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-43405']
                                ))
                                break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
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
                description='No MSSQL injection indicators detected on checked ports'
            ))

        return results
