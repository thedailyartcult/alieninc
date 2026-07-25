"""
Plugin 1120: GraphQL Introspection Query Detection
====================================================
Detects exposed GraphQL endpoints with introspection enabled.
Introspection allows querying the entire API schema, revealing
types, queries, mutations, and subscriptions.
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class GraphqlIntrospectionDetection(NaslPlugin):
    PLUGIN_ID = 1120
    NAME = 'GraphQL Introspection Query Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects exposed GraphQL endpoints with introspection enabled. GraphQL '
        'introspection allows querying the schema, types, queries, mutations, and '
        'subscriptions, revealing the entire API surface. This information helps '
        'attackers find vulnerable endpoints to exploit.'
    )
    SOLUTION = (
        'Disable introspection in production. Use authentication on the GraphQL '
        'endpoint. Implement query depth limiting and rate limiting.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443, 4000]

    INTROSPECTION_QUERY = (
        '{"query":"query { __schema { types { name fields { name type { name kind } } } } }"}'
    )

    GRAPHQL_ENDPOINTS = [
        '/graphql', '/api/graphql', '/gql', '/query',
        '/v1/graphql', '/v2/graphql', '/api', '/graph',
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
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    body = self.INTROSPECTION_QUERY
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

                    body_section = response.split(b'\r\n\r\n', 1)
                    body_text = body_section[1].decode('utf-8', errors='ignore') if len(body_section) > 1 else ''

                    try:
                        parsed = json.loads(body_text)
                        if 'data' in parsed and '__schema' in parsed['data']:
                            types = parsed['data']['__schema'].get('types', [])
                            if types:
                                type_names = [t.get('name', '') for t in types if t.get('name')]
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='medium',
                                    description=f'GraphQL introspection enabled at {endpoint}',
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, schema types exposed: {len(type_names)} types found',
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

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No GraphQL introspection detected on checked ports'
            ))

        return results
