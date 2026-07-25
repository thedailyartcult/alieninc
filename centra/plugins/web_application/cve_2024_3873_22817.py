import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20243873Plugin(NaslPlugin):
    PLUGIN_ID = 22817
    NAME = "CVE-2024-3873"
    DESCRIPTION = "A vulnerability was found in SMI SMI-EX-5414W up to 1.0.03. It has been classified as problematic. This affects an unknown part of the component Web Interface. The manipulation leads to cross-site req"
    SOLUTION = "Apply vendor patch for CVE-2024-3873. Upgrade to latest version."
    CVSS_SCORE = 4.3
    FAMILY = "Web Application"
    CVE = ['CVE-2024-3873']
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}\r\n"
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
                if "HTTP/1.1 200" in body or "HTTP/1.1 403" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.severity_from_cvss(self.CVSS_SCORE),
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="CVE-2024-3873 check — response received",
                        references=['CVE-2024-3873']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                pass
        return results
