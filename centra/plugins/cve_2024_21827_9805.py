import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202421827Plugin(NaslPlugin):
    PLUGIN_ID = 9805
    NAME = "CVE-2024-21827"
    DESCRIPTION = "A leftover debug code vulnerability exists in the cli_server debug functionality of Tp-Link ER7206 Omada Gigabit VPN Router 1.4.1 Build 20240117 Rel.57421. A specially crafted series of network reques"
    SOLUTION = "Apply vendor patch for CVE-2024-21827. Upgrade to latest version."
    CVSS_SCORE = 7.2
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-21827']
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
                if "Tp-Link:ER7206 Omada Gigabit VPN Router" in banner_str:
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
