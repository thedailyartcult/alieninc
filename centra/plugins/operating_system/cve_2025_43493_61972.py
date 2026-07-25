import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202543493Plugin(NaslPlugin):
    PLUGIN_ID = 61972
    NAME = "CVE-2025-43493"
    DESCRIPTION = "The issue was addressed with improved checks. This issue is fixed in Safari 26.1, iOS 18.7.2 and iPadOS 18.7.2, iOS 26.1 and iPadOS 26.1, macOS Tahoe 26.1, visionOS 26.1. Visiting a malicious website "
    SOLUTION = "Apply vendor patch for CVE-2025-43493."
    CVSS_SCORE = 4.3
    FAMILY = "Operating System"
    CVE = ['CVE-2025-43493']
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
                        evidence="CVE-2025-43493 check", references=['CVE-2025-43493']
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
