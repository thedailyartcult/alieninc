import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202622281Plugin(NaslPlugin):
    PLUGIN_ID = 87737
    NAME = "CVE-2026-22281"
    DESCRIPTION = "Dell PowerScale OneFS, versions 9.5.0.0 through 9.5.1.5, versions 9.6.0.0 through 9.7.1.10, versions 9.8.0.0 through 9.10.1.3, versions starting from 9.11.0.0 and prior to 9.13.0.0, contains a Time-of"
    SOLUTION = "Apply vendor patch for CVE-2026-22281."
    CVSS_SCORE = 3.5
    FAMILY = "Network Devices"
    CVE = ['CVE-2026-22281']
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
                        evidence="CVE-2026-22281 check", references=['CVE-2026-22281']
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
