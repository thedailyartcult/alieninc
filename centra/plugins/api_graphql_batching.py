import asyncio
import json
import ssl
from plugins import NaslPlugin, PluginResult

class GraphQLBatching(NaslPlugin):
    PLUGIN_ID = 1254
    NAME = 'GraphQL Batching / Rate Limit Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Detects vulnerability to GraphQL batching attacks where multiple queries are sent in a single request via batched query arrays or aliases. Batching bypasses per-request rate limits, allowing attackers to brute force data at high speed.'
    SOLUTION = 'Implement query cost analysis and rate limiting per query cost, not per request. Limit the number of queries in a batch request. Implement operation name whitelisting.'
    CVE = []
    PORTS = [80, 443, 8080, 8443, 4000]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        graphql_endpoints = ['/graphql', '/api/graphql', '/graphiql', '/graphql/v1', '/gql', '/query', '/api/query']
        queries = [
            {'query': '{ __schema { types { name } } }'},
            {'query': '{ users { id name } }'},
            {'query': '{ products { id title } }'},
        ]
        batched_queries = json.dumps([{'query': '{ __schema { types { name } } }'}, {'query': '{ __schema { queryType { name } } }'}, {'query': '{ __schema { mutationType { name } } }'}])
        aliased_query = '{"query": "query { a: __schema { types { name } } b: __schema { queryType { name } } c: __schema { mutationType { name } } }"}'
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for ep in graphql_endpoints:
                for label, payload in [('batched', batched_queries), ('aliased', aliased_query)]:
                    try:
                        ctx = None
                        scheme = 'https' if port_to_check in (443, 8443, 4000) else 'http'
                        if scheme == 'https':
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                        req = f'POST {ep} HTTP/1.1\r\nHost: {host_header}\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n{payload}'
                        writer.write(req.encode())
                        await writer.drain()
                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk: break
                                response += chunk
                                if len(response) > 16384: break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()
                        if response:
                            status = int(response.split(b'\r\n')[0].split(b' ')[1])
                            body = response[response.find(b'\r\n\r\n')+4:].decode(errors='replace')
                            if status == 200:
                                try:
                                    resp_data = json.loads(body)
                                    if label == 'batched' and isinstance(resp_data, list) and len(resp_data) > 1:
                                        results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'GraphQL batching accepted at {ep}: {len(resp_data)} queries in single request. Rate limit bypass possible.'))
                                        found = True
                                        break
                                    if label == 'aliased' and isinstance(resp_data, dict) and 'data' in resp_data:
                                        data = resp_data['data']
                                        if isinstance(data, dict) and sum(1 for v in data.values() if v is not None) > 1:
                                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'GraphQL aliased queries accepted at {ep}. Multiple queries via aliasing bypasses rate limits.'))
                                            found = True
                                            break
                                except (json.JSONDecodeError, TypeError):
                                    pass
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if found: break
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No GraphQL batching vulnerability detected'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
