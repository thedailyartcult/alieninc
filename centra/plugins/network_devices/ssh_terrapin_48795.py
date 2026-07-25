import asyncio
from plugins import NaslPlugin, PluginResult


class SshTerrapinPlugin(NaslPlugin):
    PLUGIN_ID = 1338
    NAME = "SSH Terrapin Prefix Truncation Attack (CVE-2023-48795)"
    DESCRIPTION = "SSH protocol vulnerability allows a man-in-the-middle attacker to truncate the extension info message during the handshake, downgrading the connection security. Affects most SSH implementations before patches."
    SOLUTION = "Apply vendor patches. Update OpenSSH to 9.6+, libssh to 0.10.6+, or paramiko to 3.4.0+. Use strict key exchange extension (RFC 8709)."
    CVSS_SCORE = 5.9
    SEVERITY = "Medium"
    FAMILY = "Network Devices"
    CVE = ["CVE-2023-48795"]
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
                        vulnerable = (major < 9) or (major == 9 and minor < 6)
                        if vulnerable:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} OpenSSH {major}.{minor}p on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"SSH banner: {banner_str.strip()}",
                                references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=p,
                                cvss_score=0, severity="Info",
                                description=f"OpenSSH {major}.{minor}p - not vulnerable",
                                solution="", evidence="", references=[]
                            ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=p,
                            cvss_score=0, severity="Info",
                            description=f"SSH detected but version unknown",
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
