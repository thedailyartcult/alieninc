import asyncio
from plugins import NaslPlugin, PluginResult


class TeamCityAuthBypassPlugin(NaslPlugin):
    PLUGIN_ID = 1296
    NAME = "JetBrains TeamCity Authentication Bypass"
    DESCRIPTION = "JetBrains TeamCity < 2023.11.4 contains an authentication bypass vulnerability in the server-side request processing that allows an unauthenticated attacker to access any endpoint, potentially leading to remote code execution."
    SOLUTION = "Upgrade TeamCity to version 2023.11.4 or later."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-27198"]
    PORTS = [80, 443, 8111, 8112]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                path = "/app/rest/server"
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
                if "HTTP/1.1 200" in body and ("serverVersion" in body or "buildNumber" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} TeamCity REST API accessible without auth on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Unauthenticated access to {path} returned server info: {body[:500]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not vulnerable to TeamCity auth bypass",
                        solution="",
                        evidence="",
                        references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect to target",
                    solution="",
                    evidence="",
                    references=[]
                ))
        return results
