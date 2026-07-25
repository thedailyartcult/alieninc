import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202536360Plugin(NaslPlugin):
    PLUGIN_ID = 58460
    NAME = "CVE-2025-36360"
    DESCRIPTION = "IBM UCD - IBM UrbanCode Deploy 7.1 through 7.1.2.27, 7.2 through 7.2.3.20, and 7.3 through 7.3.2.15 and IBM UCD - IBM DevOps Deploy 8.0 through 8.0.1.10, and 8.1 through 8.1.2.3 is susceptible to a ra"
    SOLUTION = "Apply vendor patch for CVE-2025-36360."
    CVSS_SCORE = 5.0
    FAMILY = "Network Devices"
    CVE = ['CVE-2025-36360']
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
                        evidence="CVE-2025-36360 check", references=['CVE-2025-36360']
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
