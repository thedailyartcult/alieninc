import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20244021Plugin(NaslPlugin):
    PLUGIN_ID = 23866
    NAME = "CVE-2024-4021"
    DESCRIPTION = "A vulnerability was found in Keenetic KN-1010, KN-1410, KN-1711, KN-1810 and KN-1910 up to 4.1.2.15. It has been declared as problematic. Affected by this vulnerability is an unknown functionality of "
    SOLUTION = "Apply vendor patch for CVE-2024-4021. Upgrade to latest version."
    CVSS_SCORE = 5.3
    FAMILY = "Web Application"
    CVE = ['CVE-2024-4021']
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
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="CVE-2024-4021 check — response received",
                        references=['CVE-2024-4021']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                pass
        return results
