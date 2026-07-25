import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20243016Plugin(NaslPlugin):
    PLUGIN_ID = 15981
    NAME = "CVE-2024-3016"
    DESCRIPTION = "NEC Platforms DT900 and DT900S Series 5.0.0.0 – v5.3.4.4, v5.4.0.0 – v5.6.0.20 allows an attacker to access a non-documented the system settings to change settings via local network with unauthenticat"
    SOLUTION = "Apply vendor patch for CVE-2024-3016. Upgrade to latest version."
    CVSS_SCORE = 9.1
    SEVERITY = "Critical"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-3016']
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
                if "NEC Platforms, Ltd:ITK-6DGS-1(BK) TEL" in banner_str:
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
