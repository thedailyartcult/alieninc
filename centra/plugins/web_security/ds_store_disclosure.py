import asyncio
from plugins import NaslPlugin, PluginResult


class DsStoreDisclosurePlugin(NaslPlugin):
    PLUGIN_ID = 1364
    NAME = ".DS_Store File Information Disclosure"
    DESCRIPTION = "Detects exposed .DS_Store files on web servers that can leak directory structure, file names, and metadata about the web application, aiding attackers in reconnaissance."
    SOLUTION = "Configure web server to block .DS_Store files. Add '~$' and '.DS_Store' to deny lists. Remove all .DS_Store files from production."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/.DS_Store", "/.ds_store", "/images/.DS_Store", "/css/.DS_Store", "/js/.DS_Store"]:
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
                    if "HTTP/1.1 200" in body and len(body) > 100:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} .DS_Store exposed at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f".DS_Store file accessible at {path} ({len(body)} bytes)",
                            references=["https://owasp.org/www-project-web-security-testing-guide/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No .DS_Store exposure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
