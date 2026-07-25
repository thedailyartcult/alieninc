import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20240220Plugin(NaslPlugin):
    PLUGIN_ID = 2863
    NAME = "CVE-2024-0220"
    DESCRIPTION = "B&R Automation Studio Upgrade Service and B&R Technology Guarding use insufficient cryptography for communication to the upgrade and the licensing servers. A network-based attacker could exploit the v"
    SOLUTION = "Apply vendor patch for CVE-2024-0220. Upgrade to latest version."
    CVSS_SCORE = 8.3
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-0220']
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                banner = await asyncio.wait_for(reader.read(256), timeout=3)
                writer.close()
                await writer.wait_closed()
                banner_str = banner.decode("utf-8", errors="replace")
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                if "B&R Industrial Automation:Automation Stu" in banner_str:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Banner: {banner_str[:200]}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
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
