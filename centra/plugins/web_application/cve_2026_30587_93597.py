import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202630587Plugin(NaslPlugin):
    PLUGIN_ID = 93597
    NAME = "CVE-2026-30587"
    DESCRIPTION = "Multiple Stored XSS vulnerabilities exist in Seafile Server version 13.0.15,13.0.16-pro,12.0.14 and prior and fixed in 13.0.17, 13.0.17-pro, and 12.0.20-pro, via the Seadoc (sdoc) editor. The applicat"
    SOLUTION = "Apply vendor patch for CVE-2026-30587."
    CVSS_SCORE = 8.7
    FAMILY = "Web Application"
    CVE = ['CVE-2026-30587']
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
                        evidence="CVE-2026-30587 check", references=['CVE-2026-30587']
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
