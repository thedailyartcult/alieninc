import asyncio
from plugins import NaslPlugin, PluginResult


class OpenSshRegresshionPlugin(NaslPlugin):
    PLUGIN_ID = 1336
    NAME = "OpenSSH regreSSHion RCE (CVE-2024-6387)"
    DESCRIPTION = "OpenSSH < 9.8p1 contains a signal handler race condition vulnerability in sshd that allows an unauthenticated attacker to achieve remote code execution as root on glibc-based Linux systems."
    SOLUTION = "Upgrade OpenSSH to version 9.8p1 or later. Apply vendor patches immediately. Restrict SSH access via firewall rules as a temporary mitigation."
    CVSS_SCORE = 8.1
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-6387"]
    PORTS = [22, 2222]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=10
                )
                banner = await asyncio.wait_for(reader.read(256), timeout=5)
                writer.close()
                await writer.wait_closed()
                banner_str = banner.decode("utf-8", errors="replace")
                if "SSH" in banner_str or "OpenSSH" in banner_str:
                    import re
                    m = re.search(r'OpenSSH[_-](\d+)\.(\d+)', banner_str)
                    if m:
                        major, minor = int(m.group(1)), int(m.group(2))
                        vulnerable = (major < 9) or (major == 9 and minor < 8) or (major == 4 and minor < 9)
                        if vulnerable:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} OpenSSH {major}.{minor}p detected on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"SSH banner: {banner_str.strip()}",
                                references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=p,
                                cvss_score=0, severity="Info",
                                description=f"OpenSSH {major}.{minor}p - not vulnerable",
                                solution="", evidence=f"Banner: {banner_str.strip()}", references=[]
                            ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=p,
                            cvss_score=0, severity="Info",
                            description=f"SSH service detected but version not parseable",
                            solution="", evidence=f"Banner: {banner_str.strip()}", references=[]
                        ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Port {p} not running SSH",
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
