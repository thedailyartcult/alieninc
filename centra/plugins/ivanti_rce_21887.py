import asyncio
from plugins import NaslPlugin, PluginResult


class IvantiRcePlugin(NaslPlugin):
    PLUGIN_ID = 1341
    NAME = "Ivanti Connect Secure RCE (CVE-2024-21887)"
    DESCRIPTION = "Ivanti Connect Secure (ICS) and Ivanti Policy Secure versions before 22.4R2.2, 22.3R1.3, 21.4R2.2 contain a command injection vulnerability in the web component that allows an authenticated attacker to execute arbitrary commands."
    SOLUTION = "Apply Ivanti patches per advisory. Upgrade to 22.4R2.2, 22.3R1.3, or 21.4R2.2. Use EDR/XDR to detect abuse."
    CVSS_SCORE = 9.1
    SEVERITY = "Critical"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-21887"]
    PORTS = [443, 8443]

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
                if "Ivanti" in body or "Connect Secure" in body or "Pulse Secure" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Ivanti ICS/Pulse Secure detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Ivanti/Pulse Secure page: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Not Ivanti/Pulse Secure on port {p}",
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
