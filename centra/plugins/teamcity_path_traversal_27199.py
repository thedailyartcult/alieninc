import asyncio
from plugins import NaslPlugin, PluginResult


class TeamCityPathTraversal27199Plugin(NaslPlugin):
    PLUGIN_ID = 1305
    NAME = "JetBrains TeamCity Path Traversal (CVE-2024-27199)"
    DESCRIPTION = "JetBrains TeamCity < 2023.11.4 contains a path traversal vulnerability in the file upload component that allows an unauthenticated attacker to read or write arbitrary files on the server."
    SOLUTION = "Upgrade TeamCity to version 2023.11.4 or later."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-27199"]
    PORTS = [80, 443, 8111, 8112]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /login.html HTTP/1.1\r\n"
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
                if "TeamCity" in body or "teamcity" in body.lower():
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} TeamCity login page exposed on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"TeamCity login page: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running TeamCity",
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
