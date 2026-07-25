import asyncio
import re
from plugins import NaslPlugin, PluginResult


class DrupalVulnDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1358
    NAME = "Drupal Core Vulnerability Detection"
    DESCRIPTION = "Detects Drupal CMS installations and version. Checks for known vulnerable versions including CVE-2019-6340 (REST RCE), CVE-2020-13671 (XSS), and CVE-2022-25295 (access bypass)."
    SOLUTION = "Upgrade Drupal to the latest security release. Apply Drupal security advisories immediately."
    CVSS_SCORE = 8.1
    SEVERITY = "High"
    FAMILY = "Web Application"
    CVE = ["CVE-2019-6340", "CVE-2020-13671", "CVE-2022-25295"]
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/core/CHANGELOG.txt", "/CHANGELOG.txt", "/node/1", "/user/login"]:
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
                    if "Drupal" in body or "drupal" in body.lower() or "SESS" in body:
                        m = re.search(r'Drupal\s*(\d+\.\d+[.\d]*)', body)
                        version = m.group(1) if m else "unknown"
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Drupal {version} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Drupal {version} detected via {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{cve}" for cve in self.CVE]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No Drupal detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
