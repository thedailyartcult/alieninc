import asyncio
from plugins import NaslPlugin, PluginResult


class RestApiAuthEnforcementPlugin(NaslPlugin):
    PLUGIN_ID = 1316
    NAME = "REST API Authentication Enforcement"
    DESCRIPTION = "Checks if REST API endpoints enforce authentication by sending unauthenticated requests to common API paths. APIs without auth allow anonymous access to potentially sensitive data."
    SOLUTION = "Implement authentication for all API endpoints using API keys, JWT, or OAuth 2.0. Do not expose internal APIs without auth checks."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        api_paths = [
            "/api/users", "/api/v1/users", "/api/v2/users",
            "/api/admin", "/api/v1/admin", "/api/config",
            "/api/settings", "/api/health", "/api/status",
            "/api/version", "/api/info", "/api/data",
            "/api/orders", "/api/products", "/api/customers",
        ]
        for p in ([port] if port else self.PORTS):
            exposed = []
            for path in api_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: application/json\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body:
                        has_json = any(sig in body for sig in ["{", "[", '"', ":", "id", "name", "email", "data"])
                        if has_json:
                            exposed.append(path)
                except Exception:
                    continue
            if exposed:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} {len(exposed)} API endpoints accessible without auth on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Unauthenticated endpoints: {', '.join(exposed)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No unauthenticated API endpoints detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
