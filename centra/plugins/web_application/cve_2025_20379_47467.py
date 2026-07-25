import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202520379Plugin(NaslPlugin):
    PLUGIN_ID = 47467
    NAME = "CVE-2025-20379"
    DESCRIPTION = "In Splunk Enterprise versions below 10.0.1, 9.4.5, 9.3.7, and 9.2.9 and Splunk Cloud Platform versions below 9.3.2411.116, 9.3.2408.124, 10.0.2503.5 and 10.1.2507.1, a low-privileged user that does no"
    SOLUTION = "Apply vendor patch for CVE-2025-20379."
    CVSS_SCORE = 3.5
    FAMILY = "Web Application"
    CVE = ['CVE-2025-20379']
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
                        description=self.DESCRIPTION, solution=self.SOLUTION,
                        evidence="CVE-2025-20379 check", references=['CVE-2025-20379']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected", solution="", evidence="", references=[]
                    ))
            except Exception:
                pass
        return results
