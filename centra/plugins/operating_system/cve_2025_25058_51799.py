import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202525058Plugin(NaslPlugin):
    PLUGIN_ID = 51799
    NAME = "CVE-2025-25058"
    DESCRIPTION = "Improper initialization for some ESXi kernel mode driver for the Intel(R) Ethernet 800-Series before version 2.2.2.0 (esxi 8.0) &amp; 2.2.3.0 (esxi 9.0) within Ring 1: Device Drivers may allow an info"
    SOLUTION = "Apply vendor patch for CVE-2025-25058."
    CVSS_SCORE = 3.3
    FAMILY = "Operating System"
    CVE = ['CVE-2025-25058']
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
                        evidence="CVE-2025-25058 check", references=['CVE-2025-25058']
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
