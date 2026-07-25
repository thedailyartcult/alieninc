import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202427256Plugin(NaslPlugin):
    PLUGIN_ID = 13891
    NAME = "CVE-2024-27256"
    DESCRIPTION = "IBM MQ Container 3.0.0, 3.0.1, 3.1.0 through 3.1.3 CD, 2.0.0 LTS through 2.0.22 LTS and 2.4.0 through 2.4.8, 2.3.0 through 2.3.3, 2.2.0 through 2.2.2 uses weaker than expected cryptographic algorithms"
    SOLUTION = "Apply vendor patch for CVE-2024-27256. Upgrade to latest version."
    CVSS_SCORE = 5.9
    SEVERITY = "Medium"
    FAMILY = "General Vulnerability"
    CVE = ['CVE-2024-27256']
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {target}:{p}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                if "HTTP/1.1 200" in body or "HTTP/1.1 401" in body or "HTTP/1.1 403" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Path accessible: /",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
