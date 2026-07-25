import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202428957Plugin(NaslPlugin):
    PLUGIN_ID = 15102
    NAME = "CVE-2024-28957"
    DESCRIPTION = "Generation of predictable identifiers issue exists in Cente middleware TCP/IP Network Series. If this vulnerability is exploited, a remote unauthenticated attacker may interfere communications by pred"
    SOLUTION = "Apply vendor patch for CVE-2024-28957. Upgrade to latest version."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-28957']
    PORTS = [22, 23, 21, 25, 161, 53, 80, 443]

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
                if "DMG MORI Digital Co., LTD. and NEXT Co.," in banner_str:
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
