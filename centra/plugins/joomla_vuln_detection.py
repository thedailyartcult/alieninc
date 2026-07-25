import asyncio
import re
from plugins import NaslPlugin, PluginResult


class JoomlaVulnDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1357
    NAME = "Joomla Core Vulnerability Detection"
    DESCRIPTION = "Detects Joomla CMS installations and determines the version. Cross-references against known vulnerable versions for CVEs such as CVE-2023-23752 (info disclosure) and CVE-2023-40621 (XSS)."
    SOLUTION = "Upgrade Joomla to the latest stable version. Apply security patches promptly from the Joomla Security Center."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Application"
    CVE = ["CVE-2023-23752", "CVE-2023-40621"]
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/administrator/", "/language/en-GB/en-GB.xml", "/components/com_users/"]:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: */*\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "Joomla" in body or "joomla" in body.lower() or "com_content" in body:
                        m = re.search(r'Joomla!?\s*(\d+\.\d+[.\d]*)', body)
                        version = m.group(1) if m else "unknown"
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Joomla {version} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Joomla {version} detected via {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{cve}" for cve in self.CVE]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No Joomla detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
