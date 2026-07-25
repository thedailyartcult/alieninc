"""
Plugin 1271: MongoDB NoSQL Injection Detection
================================================
Detects MongoDB NoSQL injection vulnerabilities by injecting JSON operators
($ne, $gt, $where) in query parameters to bypass authentication or extract data.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class MongoDBNoSQLInjection(NaslPlugin):
    PLUGIN_ID = 1271
    NAME = 'MongoDB NoSQL Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects MongoDB NoSQL injection vulnerabilities by injecting JSON '
        'operators ($ne, $gt, $where) in query parameters to bypass '
        'authentication or extract data.'
    )
    SOLUTION = (
        'Validate and sanitize all JSON inputs. Avoid passing raw user input '
        'to MongoDB queries. Use strict typing and schema validation. Implement '
        'proper authentication checks server-side.'
    )
    CVE = ['CVE-2024-22393']
    PORTS = [80, 443, 8080, 8443, 27017]

    PAYLOADS = [
        ('{"$ne": ""}', 'not equal'),
        ('{"$gt": ""}', 'greater than'),
        ('{"$where": "1==1"}', 'where clause'),
        ('{"$regex": ".*"}', 'regex'),
    ]

    PARAMS = ['username', 'password', 'user', 'pass', 'q', 'email', 'token']
    LOGIN_PARAMS = ['username', 'password', 'user']

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
                    for payload, ptype in self.PAYLOADS:
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

                            header_section = response.split(b'\r\n\r\n', 1)[0] if b'\r\n\r\n' in response else response
                            body = response.split(b'\r\n\r\n', 1)
                            body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                            status_line = header_section.split(b'\r\n')[0].decode('utf-8', errors='ignore') if header_section else ''
                            status_code = 0
                            if ' ' in status_line:
                                try:
                                    status_code = int(status_line.split(' ')[1])
                                except (IndexError, ValueError):
                                    pass

                            if status_code in (200, 302) and (len(body_text) > 50 or 'welcome' in body_text.lower() or 'dashboard' in body_text.lower()):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='high',
                                    description=f'MongoDB NoSQL injection possible via param "{param}"',
                                    solution=self.SOLUTION,
                                    evidence=f'Payload: {payload} ({ptype}), authentication may be bypassed',
                                    references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-22393']
                                ))
                                break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break
                if results:
                    break

                if not results:
                    for param in self.LOGIN_PARAMS:
                        for payload in ['{"$ne": ""}', '{"$gt": ""}']:
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                encoded_wrong = urllib.parse.quote('wrong')
                                req1 = (
                                    f'GET /login?{param}=admin&password={encoded_wrong} HTTP/1.1\r\n'
                                    f'Host: {host_header}\r\n'
                                    f'User-Agent: Centra/1.0\r\n'
                                    f'Connection: close\r\n\r\n'
                                )
                                writer.write(req1.encode())
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

                                body1 = response.split(b'\r\n\r\n', 1)
                                t1 = body1[1].decode('utf-8', errors='ignore') if len(body1) > 1 else ''

                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target, port_to_check, ssl=ctx),
                                    timeout=5
                                )
                                encoded_payload = urllib.parse.quote(payload)
                                req2 = (
                                    f'GET /login?{param}={encoded_payload}&password={encoded_payload} HTTP/1.1\r\n'
                                    f'Host: {host_header}\r\n'
                                    f'User-Agent: Centra/1.0\r\n'
                                    f'Connection: close\r\n\r\n'
                                )
                                writer.write(req2.encode())
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

                                body2 = response.split(b'\r\n\r\n', 1)
                                t2 = body2[1].decode('utf-8', errors='ignore') if len(body2) > 1 else ''

                                if len(t2) != len(t1) or 'invalid' not in t2.lower():
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='medium',
                                        description='Possible NoSQL injection - JSON operator injection returned different response',
                                        solution=self.SOLUTION,
                                        evidence=f'Potential NoSQL injection via {param} parameter with operator injection',
                                        references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-22393']
                                    ))
                                    break
                            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                                pass
                        if results:
                            break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No MongoDB NoSQL injection indicators detected on checked ports'
            ))

        return results
