import asyncio
from plugins import NaslPlugin, PluginResult


class ColdFusionRce38203Plugin(NaslPlugin):
    PLUGIN_ID = 1300
    NAME = "Adobe ColdFusion RCE (CVE-2023-38203)"
    DESCRIPTION = "Adobe ColdFusion versions 2016u16, 2018u12, 2021u2 and earlier contain a deserialization of untrusted data vulnerability that allows an unauthenticated attacker to achieve remote code execution."
    SOLUTION = "Upgrade ColdFusion to version 2016u17, 2018u13, 2021u3 or later. Apply APSB23-40."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2023-38203"]
    PORTS = [80, 443, 8500, 8700]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /CFIDE/administrator/index.cfm HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                if "HTTP/1.1 200" in body and ("ColdFusion" in body or "CFIDE" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} ColdFusion admin interface exposed on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"ColdFusion admin page accessible: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running ColdFusion",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect to target",
                    solution="", evidence="", references=[]
                ))
        return results
