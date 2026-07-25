"""
Plugin 1228: GraphQL SQL/NoSQL Injection Detection
====================================================
Detects SQL and NoSQL injection vulnerabilities in GraphQL endpoints
by injecting injection payloads into GraphQL query arguments.
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class GraphqlInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1228
    NAME = 'GraphQL SQL/NoSQL Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects SQL and NoSQL injection vulnerabilities in GraphQL endpoints '
        'by injecting injection payloads into GraphQL query arguments. GraphQL '
        'injection can extract data from connected databases through the API layer.'
    )
    SOLUTION = (
        'Use parameterized queries in GraphQL resolvers. Apply input validation '
        'and sanitization. Use query depth limiting. Implement proper authorization '
        'in resolvers.'
    )
    CVE = ['CVE-2023-31418']
    PORTS = [80, 443, 8080, 8443, 4000]

    GRAPHQL_ENDPOINTS = [
        '/graphql', '/api/graphql', '/gql', '/query',
        '/v1/graphql', '/v2/graphql', '/api', '/graph',
    ]

    INJECTION_QUERIES = [
        '''{"query":"query { user(id: \\"1' OR '1'='1\\") { name email } }"}''',
        '''{"query":"query { search(q: \\"' OR 1=1 --\\") { results } }"}''',
        '''{"query":"query { item(id: \\"1' UNION SELECT * FROM users --\\") { title } }"}''',
        '''{"query":"query { findUser(email: \\"' || '1'=='1\\") { name } }"}''',
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

                for endpoint in self.GRAPHQL_ENDPOINTS:
                    for query_body in self.INJECTION_QUERIES:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )

                            req = (
                                f'POST {endpoint} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Content-Type: application/json\r\n'
                                f'Content-Length: {len(query_body)}\r\n'
                                f'User-Agent: Centra/1.0\r\n'
                                f'Connection: close\r\n\r\n'
                                f'{query_body}'
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
                                    if len(response) > 32768:
                                        break
                            except asyncio.TimeoutError:
                                pass
                            writer.close()
                            await writer.wait_closed()

                            body_section = response.split(b'\r\n\r\n', 1)
                            body_text = body_section[1].decode('utf-8', errors='ignore') if len(body_section) > 1 else ''

                            try:
                                parsed = json.loads(body_text)
                                if 'errors' in parsed:
                                    for err in parsed['errors']:
                                        msg = err.get('message', '')
                                        indicators = ['sql', 'unexpected', 'syntax', 'invalid input',
                                                      'unknown column', 'where clause']
                                        if any(ind in msg.lower() for ind in indicators):
                                            results.append(PluginResult(
                                                vulnerable=True,
                                                target=target,
                                                port=port_to_check,
                                                cvss_score=self.CVSS_SCORE,
                                                severity='high',
                                                description=f'GraphQL injection detected at {endpoint}',
                                                solution=self.SOLUTION,
                                                evidence=f'Endpoint: {endpoint}, query: {query_body[:80]}..., error: {msg[:200]}',
                                                references=[
                                                    'https://portswigger.net/web-security/graphql',
                                                ]
                                            ))
                                            break
                                if results:
                                    break
                            except (json.JSONDecodeError, KeyError):
                                pass
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No GraphQL injection indicators detected on checked ports'
            ))

        return results
