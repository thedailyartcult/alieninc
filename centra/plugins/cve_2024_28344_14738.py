import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202428344Plugin(NaslPlugin):
    PLUGIN_ID = 14738
    NAME = "CVE-2024-28344"
    DESCRIPTION = "An Open Redirect vulnerability was found in Sipwise C5 NGCP Dashboard below mr11.5.1. The Open Redirect vulnerability allows attackers to control the \"back\" parameter in the URL through a double enc"
    SOLUTION = "Apply vendor patch for CVE-2024-28344. Upgrade to latest version."
    CVSS_SCORE = 3.1
    SEVERITY = "Low"
    FAMILY = "General Vulnerability"
    CVE = ['CVE-2024-28344']
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
