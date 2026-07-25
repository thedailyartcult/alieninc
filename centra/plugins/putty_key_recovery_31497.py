import asyncio
from plugins import NaslPlugin, PluginResult


class PuttyKeyRecoveryPlugin(NaslPlugin):
    PLUGIN_ID = 1339
    NAME = "PuTTY SSH Key Recovery (CVE-2024-31497)"
    DESCRIPTION = "PuTTY 0.68-0.81 uses biased ECDSA nonces for NIST P-521 keys, allowing an attacker to recover the private key from a few dozen signatures. Affects Pageant and all tools using PuTTY's key generation."
    SOLUTION = "Upgrade PuTTY to version 0.82 or later. Revoke and regenerate any NIST P-521 ECDSA keys that were generated with PuTTY 0.68-0.81."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-31497"]
    PORTS = [22]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=10
                )
                banner = await asyncio.wait_for(reader.read(512), timeout=5)
                writer.close()
                await writer.wait_closed()
                banner_str = banner.decode("utf-8", errors="replace")
                if "ecdsa-sha2-nistp521" in banner_str:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} P-521 ECDSA key used on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"ECDSA P-521 key detected: {banner_str[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No P-521 ECDSA key detected on port {p}",
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
