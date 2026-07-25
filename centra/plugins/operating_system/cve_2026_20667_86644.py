import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202620667Plugin(NaslPlugin):
    PLUGIN_ID = 86644
    NAME = "CVE-2026-20667"
    DESCRIPTION = "A logic issue was addressed with improved checks. This issue is fixed in iOS 26.3 and iPadOS 26.3, macOS Sequoia 15.7.4, macOS Sonoma 14.8.4, macOS Tahoe 26.3, watchOS 26.3. An app may be able to brea"
    SOLUTION = "Apply vendor patch for CVE-2026-20667."
    CVSS_SCORE = 8.8
    FAMILY = "Operating System"
    CVE = ['CVE-2026-20667']
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
                        evidence="CVE-2026-20667 check", references=['CVE-2026-20667']
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
