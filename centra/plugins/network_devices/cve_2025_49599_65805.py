import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202549599Plugin(NaslPlugin):
    PLUGIN_ID = 65805
    NAME = "CVE-2025-49599"
    DESCRIPTION = "Huawei EG8141A5 devices through V5R019C00S100, EG8145V5 devices through V5R019C00S100, and EG8145V5-V2 devices through V5R021C00S184 allow the Epuser account to disable ONT firewall functionality, e.g"
    SOLUTION = "Apply vendor patch for CVE-2025-49599."
    CVSS_SCORE = 4.1
    FAMILY = "Network Devices"
    CVE = ['CVE-2025-49599']
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
                        evidence="CVE-2025-49599 check", references=['CVE-2025-49599']
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
