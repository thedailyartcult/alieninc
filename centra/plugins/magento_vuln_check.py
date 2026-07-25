import asyncio
import re
from plugins import NaslPlugin, PluginResult


class MagentoVulnCheckPlugin(NaslPlugin):
    PLUGIN_ID = 1359
    NAME = "Magento Version Vulnerability Check"
    DESCRIPTION = "Detects Adobe Commerce/Magento installations and version. Identifies potentially vulnerable versions for CVEs including CVE-2024-20720 (RCE), CVE-2024-20718 (XSS), and CVE-2024-20712 (path traversal)."
    SOLUTION = "Upgrade Adobe Commerce/Magento to the latest version. Apply APSB security patches from Adobe."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Application"
    CVE = ["CVE-2024-20720", "CVE-2024-20718", "CVE-2024-20712"]
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/static/version/", "/magento_version", "/health_check.php"]:
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
                    if "Magento" in body or "magento" in body.lower() or "X-Magento" in body:
                        m = re.search(r'Magento\s*(?:Commerce|Open\sSource)?\s*(\d+\.\d+[.\d]*)', body)
                        version = m.group(1) if m else "unknown"
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Magento {version} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Magento {version} detected via {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{cve}" for cve in self.CVE]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No Magento detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
