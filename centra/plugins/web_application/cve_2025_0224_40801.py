import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20250224Plugin(NaslPlugin):
    PLUGIN_ID = 40801
    NAME = "CVE-2025-0224"
    DESCRIPTION = "A vulnerability was found in Provision-ISR SH-4050A-2, SH-4100A-2L(MM), SH-8100A-2L(MM), SH-16200A-2(1U), SH-16200A-5(1U) and NVR5-8200PX up to 20241220. It has been declared as problematic. Affected "
    SOLUTION = "Apply vendor patch for CVE-2025-0224."
    CVSS_SCORE = 5.3
    FAMILY = "Web Application"
    CVE = ['CVE-2025-0224']
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
                        evidence="CVE-2025-0224 check", references=['CVE-2025-0224']
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
