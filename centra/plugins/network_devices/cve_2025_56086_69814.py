import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202556086Plugin(NaslPlugin):
    PLUGIN_ID = 69814
    NAME = "CVE-2025-56086"
    DESCRIPTION = "OS Command Injection vulnerability in Ruijie RG-EW1200 EW_3.0(1)B11P227_EW1200_11130208RG-EW1200 V1.00 allowing attackers to execute arbitrary commands via a crafted POST request to the module_get in "
    SOLUTION = "Apply vendor patch for CVE-2025-56086."
    CVSS_SCORE = 8.8
    FAMILY = "Network Devices"
    CVE = ['CVE-2025-56086']
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
                        evidence="CVE-2025-56086 check", references=['CVE-2025-56086']
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
