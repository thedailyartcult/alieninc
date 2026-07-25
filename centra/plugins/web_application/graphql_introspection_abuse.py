"""
Plugin 1274: GraphQL Introspection Query Abuse
================================================
Detects exposed GraphQL introspection queries that allow attackers to
enumerate all available types, queries, mutations, and subscriptions.
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class GraphQLIntrospectionAbuse(NaslPlugin):
    PLUGIN_ID = 1274
    NAME = 'GraphQL Introspection Query Abuse'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects exposed GraphQL introspection queries that allow attackers to '
        'enumerate all available types, queries, mutations, and subscriptions '
        'in a GraphQL API.'
    )
    SOLUTION = (
        'Disable GraphQL introspection in production. Use a whitelist approach '
        'for allowed queries. Implement query depth limiting and rate limiting. '
        'Consider using persisted queries.'
    )
    CVE = ['CVE-2024-28710']
    PORTS = [80, 443, 8080, 8443, 4000, 5000]

    INTROSPECTION_QUERY = (
        '{"query":"query { __schema { types { name fields { name type { name kind } } } } }"}'
    )

    ENDPOINTS = [
        '/graphql', '/graphql?query={__schema{types{name}}}',
        '/api/graphql', '/api', '/graph',
        '/v1/graphql', '/v2/graphql',
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

                for endpoint in self.ENDPOINTS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        body = '{"query":"__schema{types{name}}"}'
                        req = (
                            f'POST {endpoint} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/json\r\n'
                            f'Content-Length: {len(body)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                            f'{body}'
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

                        header_section = response.split(b'\r\n\r\n', 1)[0] if b'\r\n\r\n' in response else response
                        body_section = response.split(b'\r\n\r\n', 1)
                        body_text = body_section[1].decode('utf-8', errors='ignore') if len(body_section) > 1 else ''

                        status_line = header_section.split(b'\r\n')[0].decode('utf-8', errors='ignore') if header_section else ''
                        status_code = 0
                        if ' ' in status_line:
                            try:
                                status_code = int(status_line.split(' ')[1])
                            except (IndexError, ValueError):
                                pass

                        if status_code == 200:
                            try:
                                parsed = json.loads(body_text)
                                if 'data' in parsed and '__schema' in parsed.get('data', {}):
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='medium',
                                        description=f'GraphQL introspection enabled at {endpoint}',
                                        solution=self.SOLUTION,
                                        evidence=f'Endpoint: {endpoint}, schema data returned',
                                        references=[
                                            'https://graphql.org/learn/introspection/',
                                            'https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html',
                                        ]
                                    ))
                                    break
                            except (json.JSONDecodeError, KeyError):
                                pass
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if results:
                    break

                if not results:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        body = self.INTROSPECTION_QUERY
                        req = (
                            f'POST /graphql HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/json\r\n'
                            f'Content-Length: {len(body)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                            f'{body}'
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

                        if '"__schema"' in body_text or '"types"' in body_text:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='medium',
                                description='GraphQL introspection enabled at /graphql',
                                solution=self.SOLUTION,
                                evidence='GraphQL introspection enabled at /graphql. Full schema can be dumped.',
                                references=[
                                    'https://graphql.org/learn/introspection/',
                                    'https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html',
                                ]
                            ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No GraphQL introspection detected on checked ports'
            ))

        return results
