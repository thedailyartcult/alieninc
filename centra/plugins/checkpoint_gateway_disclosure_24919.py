import asyncio
from plugins import NaslPlugin, PluginResult


class CheckPointDisclosure24919Plugin(NaslPlugin):
    PLUGIN_ID = 1302
    NAME = "Check Point Security Gateway Info Disclosure"
    DESCRIPTION = "Check Point Security Gateway versions before R81.20 (May 2024) contain an information disclosure vulnerability in the IPSec VPN component that allows an unauthenticated attacker to read sensitive information."
    SOLUTION = "Upgrade Check Point Security Gateway to R81.20 or later. Apply Check Point security advisory sk182336."
    CVSS_SCORE = 8.6
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-24919"]
    PORTS = [443, 8443, 500, 4500]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
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
                if "Check Point" in body or "CPChe" in body or "SG" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Check Point Gateway detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Check Point banner: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running Check Point Gateway",
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
