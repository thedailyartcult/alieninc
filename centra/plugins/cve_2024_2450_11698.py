import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20242450Plugin(NaslPlugin):
    PLUGIN_ID = 11698
    NAME = "CVE-2024-2450"
    DESCRIPTION = "Mattermost versions 8.1.x before 8.1.10, 9.2.x before 9.2.6, 9.3.x before 9.3.2, and 9.4.x before 9.4.3 fail to correctly verify account ownership when switching from email to SAML authentication, all"
    SOLUTION = "Apply vendor patch for CVE-2024-2450. Upgrade to latest version."
    CVSS_SCORE = 8.8
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-2450']
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
                if "Mattermost:Mattermost" in banner_str:
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
