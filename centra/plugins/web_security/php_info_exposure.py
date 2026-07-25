import asyncio
from plugins import NaslPlugin, PluginResult


class PhpInfoExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1384
    NAME = "PHP Info Exposure Detection"
    DESCRIPTION = "Detects exposed phpinfo() pages that disclose detailed PHP configuration including server paths, environment variables, loaded extensions, and potentially sensitive credentials."
    SOLUTION = "Remove phpinfo() files from production servers. If needed, protect with authentication or IP restriction."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        info_paths = [
            "/info.php", "/phpinfo.php", "/test.php", "/php_info.php",
            "/p.php", "/i.php", "/infophp.php", "/info/",
        ]
        for p in ([port] if port else self.PORTS):
            for path in info_paths:
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
                    resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body and ("PHP Version" in body or "phpinfo()" in body or "PHP License" in body or "PHP Credits" in body):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} phpinfo() exposed at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"phpinfo page accessible: {path}",
                            references=["https://owasp.org/www-project-web-security-testing-guide/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No phpinfo exposure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
