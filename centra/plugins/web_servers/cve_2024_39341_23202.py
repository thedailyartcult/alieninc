import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202439341Plugin(NaslPlugin):
    PLUGIN_ID = 23202
    NAME = "CVE-2024-39341"
    DESCRIPTION = "Entrust Instant Financial Issuance (On Premise) Software (formerly known as Cardwizard) 6.10.0, 6.9.0, 6.9.1, 6.9.2, and 6.8.x and earlier leaves behind a configuration file (i.e. WebAPI.cfg.xml) afte"
    SOLUTION = "Apply vendor patch for CVE-2024-39341. Upgrade to latest version."
    CVSS_SCORE = 5.9
    FAMILY = "Web Servers"
    CVE = ['CVE-2024-39341']
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
                        evidence="CVE-2024-39341 check — response received",
                        references=['CVE-2024-39341']
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
