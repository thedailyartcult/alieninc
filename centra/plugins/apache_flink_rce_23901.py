import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheFlinkRce23901Plugin(NaslPlugin):
    PLUGIN_ID = 1374
    NAME = "Apache Flink Remote Code Execution (CVE-2024-23901)"
    DESCRIPTION = "Apache Flink < 1.17.2, 1.18.1, 1.19.0 contain a remote code execution vulnerability in the job submission REST API that allows an authenticated attacker to execute arbitrary code on the TaskManager."
    SOLUTION = "Upgrade Apache Flink to 1.17.2, 1.18.1, 1.19.0 or later. Restrict access to Flink dashboard and REST API."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-23901"]
    PORTS = [80, 443, 8081, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/jobs/", "/taskmanagers/", "/config", "/overview"]:
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
                    if "flink" in body.lower() or "jobmanager" in body.lower() or "taskmanager" in body.lower():
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Flink dashboard accessible on port {p}: {body[:200]}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Flink not detected on port",
                    solution="", evidence="", references=[]
                ))
        return results
