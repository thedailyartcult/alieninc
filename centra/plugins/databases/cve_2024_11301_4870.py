import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202411301Plugin(NaslPlugin):
    PLUGIN_ID = 4870
    NAME = "CVE-2024-11301"
    DESCRIPTION = "In lunary-ai/lunary before version 1.6.3, the application allows the creation of evaluators without enforcing a unique constraint on the combination of projectId and slug. This allows an attacker to o"
    SOLUTION = "Apply vendor patch for CVE-2024-11301. Upgrade to latest version."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Databases"
    CVE = ['CVE-2024-11301']
    PORTS = [3306, 5432, 1521, 27017, 6379, 80, 443]

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
                if "lunary-ai:lunary-ai/lunary" in banner_str:
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
