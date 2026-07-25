import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202532916Plugin(NaslPlugin):
    PLUGIN_ID = 57438
    NAME = "CVE-2025-32916"
    DESCRIPTION = "Potential use of sensitive information in GET requests in Checkmk GmbH's Checkmk versions <2.4.0p13, <2.3.0p38, <2.2.0p46, and 2.1.0 (EOL) may cause sensitive form data to be included in URL query par"
    SOLUTION = "Apply vendor patch for CVE-2025-32916."
    CVSS_SCORE = 4.3
    FAMILY = "Web Servers"
    CVE = ['CVE-2025-32916']
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
                        evidence="CVE-2025-32916 check", references=['CVE-2025-32916']
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
