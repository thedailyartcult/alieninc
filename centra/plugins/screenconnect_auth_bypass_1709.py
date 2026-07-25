import asyncio
from plugins import NaslPlugin, PluginResult


class ScreenConnectAuthBypassPlugin(NaslPlugin):
    PLUGIN_ID = 1298
    NAME = "ConnectWise ScreenConnect Authentication Bypass"
    DESCRIPTION = "ConnectWise ScreenConnect 23.9.7 and earlier contains an authentication bypass vulnerability that allows an unauthenticated attacker to create a new administrator account and gain full control of the server."
    SOLUTION = "Upgrade ConnectWise ScreenConnect to version 23.9.8 or later immediately."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Application"
    CVE = ["CVE-2024-1709"]
    PORTS = [80, 443, 8040, 8041]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /Login HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("ScreenConnect" in body or "screenconnect" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} ScreenConnect login page exposed on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"ScreenConnect login page accessible: {body[:500]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not running ScreenConnect",
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
