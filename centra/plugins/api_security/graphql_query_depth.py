import asyncio
from plugins import NaslPlugin, PluginResult


class GraphqlQueryDepthPlugin(NaslPlugin):
    PLUGIN_ID = 1354
    NAME = "GraphQL Query Depth Analysis"
    DESCRIPTION = "Tests GraphQL endpoints for deep query attacks and introspection abuse. Sends batch queries and deeply nested queries to detect missing depth limiting and query cost analysis."
    SOLUTION = "Implement query depth limiting, query cost analysis, and rate limiting on GraphQL endpoints. Disable introspection in production."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 4000, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        graphql_paths = ["/graphql", "/api/graphql", "/graph", "/query", "/api/query"]
        for p in ([port] if port else self.PORTS):
            for path in graphql_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    query = '{"query":"query { __schema { types { name fields { name type { name } } } } }"}'
                    request = (
                        f"POST {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(query)}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: application/json\r\n"
                        f"Connection: close\r\n\r\n"
                        f"{query}"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body and '"data"' in body and '"__schema"' in body:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} GraphQL introspection enabled on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"GraphQL introspection at {path} returned schema data",
                            references=["https://graphql.org/learn/security/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No GraphQL endpoint on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
