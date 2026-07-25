import asyncio
from plugins import NaslPlugin, PluginResult


class CorsMisconfigurationPlugin(NaslPlugin):
    PLUGIN_ID = 1315
    NAME = "CORS Misconfiguration Detection"
    DESCRIPTION = "Checks for Cross-Origin Resource Sharing (CORS) misconfigurations that allow arbitrary origins, null origins, or internal origins to access sensitive resources, potentially leading to data theft."
    SOLUTION = "Restrict Access-Control-Allow-Origin to specific trusted origins. Do not use '*' or dynamically echo the Origin header without validation."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        test_origins = [
            "https://evil.com",
            "null",
            "https://{target}",
            "https://evil-{target}",
        ]
        for p in ([port] if port else self.PORTS):
            findings = []
            for origin in test_origins:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET / HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"Origin: {origin}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: */*\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    headers = resp.decode("utf-8", errors="replace")
                    headers_lower = headers.lower()
                    if "access-control-allow-origin:" in headers_lower:
                        for line in headers.split("\r\n"):
                            if "access-control-allow-origin" in line.lower():
                                allowed = line.split(":", 1)[1].strip()
                                if allowed in ["*", "null"] or allowed == origin:
                                    findings.append(f"ACAO: {allowed} (echoed from '{origin}')")
                except Exception:
                    continue
            if findings:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} CORS misconfiguration detected on port {p}",
                    solution=self.SOLUTION,
                    evidence="; ".join(findings),
                    references=["https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No CORS misconfigurations detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
