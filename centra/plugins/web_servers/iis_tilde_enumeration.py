import asyncio
from plugins import NaslPlugin, PluginResult


class IisTildeEnumerationPlugin(NaslPlugin):
    PLUGIN_ID = 1363
    NAME = "IIS Tilde Directory Enumeration Detection"
    DESCRIPTION = "Detects IIS tilde (~) character enumeration vulnerability that allows attackers to discover hidden files and directories on IIS web servers via short filename 8.3 pattern matching."
    SOLUTION = "Disable 8.3 filename generation on NTFS volumes. Apply IIS URLScan or equivalent ISAPI filter to block tilde requests."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Servers"
    CVE = ["CVE-2020-0616"]
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /~a*~1*~ HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("~1" in body or "filename" in body.lower() or "short" in body.lower()):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} IIS tilde enumeration possible on port {p}",
                        solution=self.SOLUTION,
                        evidence="IIS responded to ~ wildcard request",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No tilde enumeration on port {p}",
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
