import asyncio
from plugins import NaslPlugin, PluginResult


class SwaggerUiExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1322
    NAME = "Swagger/OpenAPI Documentation Exposure"
    DESCRIPTION = "Detects exposed Swagger UI, OpenAPI documentation, and API specification files that may leak sensitive information about API endpoints, parameters, authentication, and data models."
    SOLUTION = "Disable API documentation in production or protect it with authentication. Use VPN access for internal API docs."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        doc_paths = [
            "/swagger-ui.html", "/swagger-ui/", "/swagger-resources",
            "/v2/api-docs", "/v3/api-docs", "/api-docs",
            "/openapi.json", "/openapi.yaml", "/api/swagger",
            "/docs", "/redoc", "/api/documentation",
            "/swagger.json", "/api/v1/openapi.json",
        ]
        for p in ([port] if port else self.PORTS):
            exposed = []
            for path in doc_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: */*\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body:
                        if any(sig in body for sig in [
                            "swagger", "openapi", "api", "paths",
                            "info", "version", "title", "Swagger UI"
                        ]):
                            exposed.append(path)
                except Exception:
                    continue
            if exposed:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} {len(exposed)} API doc endpoints exposed on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Exposed docs: {', '.join(exposed)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa9-improper-assets-management/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No API documentation exposure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
