import asyncio
from plugins import NaslPlugin, PluginResult


class XWikiRce31982Plugin(NaslPlugin):
    PLUGIN_ID = 1301
    NAME = "XWiki RCE (CVE-2024-31982)"
    DESCRIPTION = "XWiki < 14.10.21, 15.0-15.5.4, 15.6-15.10.1 contains a template injection vulnerability in the document rendering that allows an authenticated user with edit rights to execute arbitrary code."
    SOLUTION = "Upgrade XWiki to version 14.10.21, 15.5.5, or 15.10.2 or later."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Application"
    CVE = ["CVE-2024-31982"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /xwiki/bin/view/Main/WebHome HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("XWiki" in body or "xwiki" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} XWiki instance detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"XWiki main page accessible: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running XWiki",
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
