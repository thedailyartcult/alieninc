import asyncio
from plugins import NaslPlugin, PluginResult


class SourceMapExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1382
    NAME = "Source Map File Exposure Detection"
    DESCRIPTION = "Detects exposed JavaScript source map files (.js.map) that can reveal the original source code, including comments and internal logic, to attackers."
    SOLUTION = "Remove source map files from production deployments. Configure web server to deny access to .map files."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Information Gathering"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        map_paths = [
            "/app.js.map", "/main.js.map", "/bundle.js.map",
            "/vendor.js.map", "/scripts.js.map", "/application.js.map",
            "/css/app.css.map", "/style.css.map",
            "/js/app.js.map", "/js/main.js.map",
        ]
        for p in ([port] if port else self.PORTS):
            for path in map_paths:
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
                    if "HTTP/1.1 200" in body and ('"sources"' in body or '"mappings"' in body or '"version"' in body):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Source map exposed at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Source map accessible: {path} ({len(body)} bytes)",
                            references=["https://owasp.org/www-project-web-security-testing-guide/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No source maps on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
