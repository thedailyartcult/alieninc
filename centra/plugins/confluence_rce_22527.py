import asyncio
from plugins import NaslPlugin, PluginResult


class ConfluenceRce22527Plugin(NaslPlugin):
    PLUGIN_ID = 1299
    NAME = "Atlassian Confluence RCE (CVE-2023-22527)"
    DESCRIPTION = "Atlassian Confluence Data Center and Server 8.0.x-8.5.4 contain an OGNL injection vulnerability in the template rendering that allows an unauthenticated attacker to execute arbitrary code."
    SOLUTION = "Upgrade Confluence to version 8.5.5 or later. Apply Atlassian security advisory AS-2024-01."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2023-22527"]
    PORTS = [80, 443, 8090, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /login.action HTTP/1.1\r\n"
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
                version_match = None
                if "Atlassian Confluence" in body:
                    import re
                    m = re.search(r'Confluence\s+(\d+\.\d+)', body)
                    if m:
                        version_match = m.group(1)
                if version_match:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Confluence {version_match} detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Confluence {version_match} login page accessible",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running Confluence",
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
