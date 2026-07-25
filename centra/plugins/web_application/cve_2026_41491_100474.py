import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202641491Plugin(NaslPlugin):
    PLUGIN_ID = 100474
    NAME = "CVE-2026-41491"
    DESCRIPTION = "Dapr is a portable, event-driven, runtime for building distributed applications across cloud and edge. From versions 1.3.0 to before 1.15.14, 1.16.0-rc.1 to before 1.16.14, and 1.17.0-rc.1 to before 1"
    SOLUTION = "Apply vendor patch for CVE-2026-41491."
    CVSS_SCORE = 8.1
    FAMILY = "Web Application"
    CVE = ['CVE-2026-41491']
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
                        evidence="CVE-2026-41491 check", references=['CVE-2026-41491']
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
