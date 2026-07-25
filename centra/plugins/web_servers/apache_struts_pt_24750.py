import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheStrutsPt24750Plugin(NaslPlugin):
    PLUGIN_ID = 1371
    NAME = "Apache Struts Path Traversal (CVE-2024-24750)"
    DESCRIPTION = "Apache Struts < 2.5.33, 6.1.2, 6.3.0.2, 2.5.32 contain a path traversal vulnerability in the file upload component that allows an attacker to write arbitrary files to the server via crafted file name parameters."
    SOLUTION = "Upgrade Apache Struts to 2.5.33, 6.1.2.1 or 6.3.0.2 or later."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-24750"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/example/", "/struts/", "/showcase/"]:
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
                    if "struts" in body.lower() or "Struts" in body or "Struts" in body:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Apache Struts detected on port {p}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Apache Struts not detected on port",
                    solution="", evidence="", references=[]
                ))
        return results
