import asyncio
from plugins import NaslPlugin, PluginResult


class ServerlessFunctionEnumerationPlugin(NaslPlugin):
    PLUGIN_ID = 1324
    NAME = "Serverless Function Endpoint Enumeration"
    DESCRIPTION = "Enumerates serverless function endpoints by probing common cloud function paths. Detects exposed AWS Lambda, Google Cloud Functions, Azure Functions, and other serverless deployments."
    SOLUTION = "Use appropriate authentication for serverless functions. Implement API Gateway-level auth. Do not expose function URLs publicly unless intended."
    CVSS_SCORE = 5.0
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        sl_paths = [
            "/.netlify/functions/", "/api/v1/", "/v1/",
            "/prod/", "/dev/", "/staging/", "/lambda/",
            "/functions/", "/api/functions/", "/.amazonaws.com/",
            "/api/function/", "/cloud-function/", "/azure-function/",
        ]
        sl_indicators = [
            "lambda", "function", "serverless", "cloudfunction",
            "azure-functions", "netlify", "vercel", "amplify",
            "cloudfront", "api-gateway", "x-amzn-",
        ]
        for p in ([port] if port else self.PORTS):
            endpoints = []
            for path in sl_paths:
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
                    if "HTTP/1.1 200" in body or "HTTP/1.1 403" in body or "HTTP/1.1 401" in body:
                        for ind in sl_indicators:
                            if ind in body.lower():
                                endpoints.append(path)
                                break
                except Exception:
                    continue
            if endpoints:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} {len(endpoints)} serverless endpoints detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Serverless paths: {', '.join(endpoints)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa9-improper-assets-management/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No serverless endpoints detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
