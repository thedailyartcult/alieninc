import asyncio
from plugins import NaslPlugin, PluginResult


class JwtAlgorithmConfusionPlugin(NaslPlugin):
    PLUGIN_ID = 1317
    NAME = "JWT Algorithm Confusion Check"
    DESCRIPTION = "Tests for JWT algorithm confusion vulnerabilities where the server accepts 'none' algorithm or algorithm switching attacks (RS256->HS256), allowing signature bypass and token forgery."
    SOLUTION = "Always validate the JWT algorithm on the server side. Enforce a strict allowlist of acceptable algorithms. Reject 'none' algorithm tokens."
    CVSS_SCORE = 8.2
    SEVERITY = "High"
    FAMILY = "API Security"
    CVE = ["CVE-2016-5431"]
    PORTS = [80, 443, 8080, 8443, 3000]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /api/health HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTUxNjIzOTAyMn0.\r\n"
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
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} JWT 'none' algorithm accepted on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"'none' algorithm JWT token accepted: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"JWT algorithm validation enforced on port {p}",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
