import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheRocketmqRce23918Plugin(NaslPlugin):
    PLUGIN_ID = 1373
    NAME = "Apache RocketMQ Remote Code Execution (CVE-2024-23918)"
    DESCRIPTION = "Apache RocketMQ < 5.1.4, 4.9.8 contain a remote code execution vulnerability in the message filtering component that allows an authenticated attacker to execute arbitrary commands via crafted filter expressions."
    SOLUTION = "Upgrade Apache RocketMQ to 5.1.4, 4.9.8 or later. Restrict access to RocketMQ console and broker ports."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-23918"]
    PORTS = [80, 443, 8080, 9876, 10911]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/rocketmq/", "/dashboard/", "/cluster"]:
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
                    if "RocketMQ" in body or "rocketmq" in body.lower():
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"RocketMQ dashboard accessible on port {p}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="RocketMQ not detected",
                    solution="", evidence="", references=[]
                ))
        return results
