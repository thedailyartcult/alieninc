import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202425623Plugin(NaslPlugin):
    PLUGIN_ID = 12491
    NAME = "CVE-2024-25623"
    DESCRIPTION = "Mastodon is a free, open-source social network server based on ActivityPub. Prior to versions 4.2.7, 4.1.15, 4.0.15, and 3.5.19, when fetching remote statuses, Mastodon doesn't check that the response"
    SOLUTION = "Apply vendor patch for CVE-2024-25623. Upgrade to latest version."
    CVSS_SCORE = 8.5
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-25623']
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
                if "mastodon:mastodon" in banner_str:
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
