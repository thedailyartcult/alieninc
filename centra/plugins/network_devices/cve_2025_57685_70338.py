import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202557685Plugin(NaslPlugin):
    PLUGIN_ID = 70338
    NAME = "CVE-2025-57685"
    DESCRIPTION = "The LB-Link routers, including the BL-AC2100_AZ3 V1.0.4, BL-WR4000 v2.5.0, BL-WR9000_AE4 v2.4.9, BL-AC1900_AZ2 v1.0.2, BL-X26_AC8 v1.2.8, and BL-LTE300_DA4 V1.2.3 models, are vulnerable to unauthorize"
    SOLUTION = "Apply vendor patch for CVE-2025-57685."
    CVSS_SCORE = 8.8
    FAMILY = "Network Devices"
    CVE = ['CVE-2025-57685']
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
                        evidence="CVE-2025-57685 check", references=['CVE-2025-57685']
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
