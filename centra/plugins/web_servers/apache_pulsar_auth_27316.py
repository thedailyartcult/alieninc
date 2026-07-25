import asyncio
from plugins import NaslPlugin, PluginResult


class ApachePulsarAuth27316Plugin(NaslPlugin):
    PLUGIN_ID = 1366
    NAME = "Apache Pulsar Authentication Bypass (CVE-2024-27316)"
    DESCRIPTION = "Apache Pulsar < 2.11.4, 3.0.0-3.0.3, 3.1.0-3.1.3 contain an authentication bypass vulnerability in the HTTP lookup endpoint that allows an unauthenticated attacker to access broker-cluster metadata and perform administrative operations."
    SOLUTION = "Upgrade Apache Pulsar to 2.11.4, 3.0.4, 3.1.4 or later. Restrict HTTP lookup endpoint to trusted networks."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-27316"]
    PORTS = [80, 443, 8080, 6650]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /admin/v2/brokers HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("brokers" in body or "pulsar" in body or "cluster" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Pulsar admin endpoint accessible without auth: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not vulnerable to Pulsar auth bypass",
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
