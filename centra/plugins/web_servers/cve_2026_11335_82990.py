import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202611335Plugin(NaslPlugin):
    PLUGIN_ID = 82990
    NAME = "CVE-2026-11335"
    DESCRIPTION = "A flaw has been found in tittuvarghese CollegeManagementSystem 3e476335cfbfb9a049e09f474c7ec885f69a9df3/a38852979f7e27ae67b610dce5979500ef8ebe01. This impacts the function session_start of the file /l"
    SOLUTION = "Apply vendor patch for CVE-2026-11335."
    CVSS_SCORE = 6.3
    FAMILY = "Web Servers"
    CVE = ['CVE-2026-11335']
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
                        evidence="CVE-2026-11335 check", references=['CVE-2026-11335']
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
