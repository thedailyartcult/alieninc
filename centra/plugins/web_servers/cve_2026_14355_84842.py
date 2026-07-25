import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202614355Plugin(NaslPlugin):
    PLUGIN_ID = 84842
    NAME = "CVE-2026-14355"
    DESCRIPTION = "In PHP versions 8.2.* before 8.2.32, 8.3.* before 8.3.32, 8.4.* before 8.4.23, 8.5.* before 8.5.8, the AES-WRAP-PAD algorithm implementation in OpenSSL extension contains a buffer allocation flaw. The"
    SOLUTION = "Apply vendor patch for CVE-2026-14355."
    CVSS_SCORE = 5.6
    FAMILY = "Web Servers"
    CVE = ['CVE-2026-14355']
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
                        evidence="CVE-2026-14355 check", references=['CVE-2026-14355']
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
