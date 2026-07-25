import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheCxfSsrf27340Plugin(NaslPlugin):
    PLUGIN_ID = 1369
    NAME = "Apache CXF SSRF (CVE-2024-27340)"
    DESCRIPTION = "Apache CXF < 3.6.3, 4.0.4 contain a Server-Side Request Forgery vulnerability in the Aegis databinding that allows an attacker to make unauthorized requests to internal systems."
    SOLUTION = "Upgrade Apache CXF to 3.6.3 or 4.0.4 or later. Disable Aegis databinding if not needed."
    CVSS_SCORE = 7.7
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-27340"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /services/ HTTP/1.1\r\n"
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
                if "Apache CXF" in body or "CXF" in body or "wsdl" in body.lower():
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Apache CXF service endpoint accessible: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Apache CXF not detected",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
