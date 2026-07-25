import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202524223Plugin(NaslPlugin):
    PLUGIN_ID = 51039
    NAME = "CVE-2025-24223"
    DESCRIPTION = "The issue was addressed with improved memory handling. This issue is fixed in Safari 18.5, iOS 18.5 and iPadOS 18.5, macOS Sequoia 15.5, tvOS 18.5, visionOS 2.5, watchOS 11.5. Processing maliciously c"
    SOLUTION = "Apply vendor patch for CVE-2025-24223."
    CVSS_SCORE = 8.0
    FAMILY = "Web Application"
    CVE = ['CVE-2025-24223']
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
                        evidence="CVE-2025-24223 check", references=['CVE-2025-24223']
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
