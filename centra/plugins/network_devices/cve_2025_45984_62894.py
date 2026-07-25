import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202545984Plugin(NaslPlugin):
    PLUGIN_ID = 62894
    NAME = "CVE-2025-45984"
    DESCRIPTION = "Blink routers BL-WR9000 V2.4.9, BL-AC1900 V1.0.2, BL-AC2100_AZ3 V1.0.4, BL-X10_AC8 V1.0.5, BL-LTE300 V1.2.3, BL-F1200_AT1 V1.0.0, BL-X26_AC8 V1.2.8, BLAC450M_AE4 V4.0.0 and BL-X26_DA3 V1.2.7 were disc"
    SOLUTION = "Apply vendor patch for CVE-2025-45984."
    CVSS_SCORE = 9.8
    FAMILY = "Network Devices"
    CVE = ['CVE-2025-45984']
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
                        evidence="CVE-2025-45984 check", references=['CVE-2025-45984']
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
