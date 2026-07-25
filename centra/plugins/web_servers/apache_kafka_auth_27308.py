import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheKafkaAuth27308Plugin(NaslPlugin):
    PLUGIN_ID = 1367
    NAME = "Apache Kafka Authentication Bypass (CVE-2024-27308)"
    DESCRIPTION = "Apache Kafka < 3.6.2, 3.7.0 contain an authentication bypass vulnerability in the Kafka Connect REST API that allows an unauthenticated attacker to create, modify, or delete connector configurations."
    SOLUTION = "Upgrade Apache Kafka to 3.6.2 or 3.7.1+. Enable authentication for the Kafka Connect REST API."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-27308"]
    PORTS = [80, 443, 8083, 8084]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /connectors HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("connectors" in body or "tasks" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Kafka Connect REST API accessible without auth: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not vulnerable to Kafka auth bypass",
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
