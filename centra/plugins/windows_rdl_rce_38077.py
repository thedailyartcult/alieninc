import asyncio
from plugins import NaslPlugin, PluginResult


class WindowsRdlRcePlugin(NaslPlugin):
    PLUGIN_ID = 1343
    NAME = "Windows Remote Desktop Licensing RCE (CVE-2024-38077)"
    DESCRIPTION = "Windows Remote Desktop Licensing Service contains a heap-based buffer overflow vulnerability that allows an unauthenticated attacker to achieve remote code execution via a specially crafted RDP licensing packet."
    SOLUTION = "Apply Microsoft security patch KB5041160 or later. Disable RDP licensing service if not needed. Restrict access to port 3389/TCP."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-38077"]
    PORTS = [3389]

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
                if "rdp" in banner_str.lower() or any(b in banner for b in [b'\x03\x00', b'\x06\x00']):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} RDP service detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"RDP service detected: {banner_str[:100]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Port {p} not running RDP",
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
