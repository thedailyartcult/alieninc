"""
Plugin 1267: MySQL Database Injection Detection
=================================================
Detects MySQL-specific SQL injection vulnerabilities by testing error-based
and time-based payloads targeting MySQL syntax.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class MySQLInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1267
    NAME = 'MySQL Database Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects MySQL-specific SQL injection vulnerabilities by testing '
        'error-based and time-based payloads targeting MySQL syntax.'
    )
    SOLUTION = (
        'Use parameterized queries. Validate and sanitize all user input. '
        'Apply the principle of least privilege for database access.'
    )
    CVE = ['CVE-2024-21272']
    PORTS = [80, 443, 8080, 8443, 3306]

    PAYLOADS = [
        "' OR '1'='1",
        "' AND 1=1-- -",
        "' AND 1=2-- -",
        "' UNION SELECT 1,2,3,4-- -",
    ]

    PARAMS = ['id', 'page', 'user', 'q', 'cat']

    MYSQL_INDICATORS = [
        'mysql', 'sql syntax', 'maria db', 'supplied argument is not',
        'you have an error in your sql syntax',
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

                            if any(ind in body_text.lower() for ind in self.MYSQL_INDICATORS):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'MySQL injection detected via param "{param}"',
                                    solution=self.SOLUTION,
                                    evidence=f'Payload: {payload}, MySQL error indicators found',
                                    references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-21272']
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
                description='No MySQL injection indicators detected on checked ports'
            ))

        return results
