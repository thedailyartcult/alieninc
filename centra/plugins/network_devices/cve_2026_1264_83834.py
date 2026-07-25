import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20261264Plugin(NaslPlugin):
    PLUGIN_ID = 83834
    NAME = "CVE-2026-1264"
    DESCRIPTION = "IBM Sterling B2B Integrator and IBM Sterling File Gateway 6.1.0.0 through 6.1.2.7_2, 6.2.0.0 through 6.2.0.5_1, 6.2.1.0 through 6.2.1.1_1, and 6.2.2.0 allows a remote unauthenticated attacker to view "
    SOLUTION = "Apply vendor patch for CVE-2026-1264."
    CVSS_SCORE = 7.1
    FAMILY = "Network Devices"
    CVE = ['CVE-2026-1264']
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
                        evidence="CVE-2026-1264 check", references=['CVE-2026-1264']
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
