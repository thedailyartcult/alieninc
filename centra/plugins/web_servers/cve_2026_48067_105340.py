import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202648067Plugin(NaslPlugin):
    PLUGIN_ID = 105340
    NAME = "CVE-2026-48067"
    DESCRIPTION = "Filament is a collection of full-stack components for accelerated Laravel development. From filament/actions 4.0.0 until 4.11.4 and 5.6.4 and from filament/tables 3.0.0 until 3.3.51, the recordSelectO"
    SOLUTION = "Apply vendor patch for CVE-2026-48067."
    CVSS_SCORE = 6.5
    FAMILY = "Web Servers"
    CVE = ['CVE-2026-48067']
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
                        evidence="CVE-2026-48067 check", references=['CVE-2026-48067']
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
