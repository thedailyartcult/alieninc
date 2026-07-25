import asyncio
from plugins import NaslPlugin, PluginResult


class ConfluencePathTraversal21644Plugin(NaslPlugin):
    PLUGIN_ID = 1304
    NAME = "Atlassian Confluence Path Traversal (CVE-2024-21644)"
    DESCRIPTION = "Atlassian Confluence Data Center and Server < 8.5.5, 8.6.0-8.7.1 contain a path traversal vulnerability that allows an authenticated attacker to read arbitrary files on the server."
    SOLUTION = "Upgrade Confluence to version 8.5.5, 8.7.2 or later."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-21644"]
    PORTS = [80, 443, 8090, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /s/ HTTP/1.1\r\n"
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
                if "Atlassian Confluence" in body or "confluence" in body.lower():
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Confluence instance detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Confluence response: {body[:300]}",
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
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
