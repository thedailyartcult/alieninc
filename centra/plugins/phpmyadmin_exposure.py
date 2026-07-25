import asyncio
from plugins import NaslPlugin, PluginResult


class PhpmyadminExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1360
    NAME = "phpMyAdmin Exposure Detection"
    DESCRIPTION = "Detects exposed phpMyAdmin interfaces which can allow attackers to execute arbitrary SQL queries and potentially gain access to the underlying database server."
    SOLUTION = "Restrict phpMyAdmin access to specific IP addresses, use authentication, or remove it from production servers entirely."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = ["CVE-2023-25713"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        pma_paths = [
            "/phpmyadmin/", "/phpMyAdmin/", "/pma/", "/PMA/",
            "/phpmyadmin/index.php", "/phpmyadmin/login.php",
            "/phpmyadmin/scripts/setup.php",
        ]
        for p in ([port] if port else self.PORTS):
            for path in pma_paths:
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
                    if "HTTP/1.1 200" in body and ("phpMyAdmin" in body or "pma_" in body or "PMA_" in body or "theme_left.css" in body):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} phpMyAdmin accessible at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"phpMyAdmin login accessible via {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No phpMyAdmin on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
