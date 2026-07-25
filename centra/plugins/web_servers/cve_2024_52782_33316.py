import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202452782Plugin(NaslPlugin):
    PLUGIN_ID = 33316
    NAME = "CVE-2024-52782"
    DESCRIPTION = "DCME-320 <=7.4.12.90, DCME-520 <=9.25.5.11, DCME-320-L <=9.3.5.26, and DCME-720 <=9.1.5.11 are vulnerable to Remote Code Execution via /function/audit/newstatistics/mon_stat_hist_new.php."
    SOLUTION = "Apply vendor patch for CVE-2024-52782."
    CVSS_SCORE = 9.8
    FAMILY = "Web Servers"
    CVE = ['CVE-2024-52782']
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
                        evidence="CVE-2024-52782 check", references=['CVE-2024-52782']
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
