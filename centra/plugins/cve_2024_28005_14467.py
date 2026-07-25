import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202428005Plugin(NaslPlugin):
    PLUGIN_ID = 14467
    NAME = "CVE-2024-28005"
    DESCRIPTION = "Aterm WG1800HP4, WG1200HS3, WG1900HP2, WG1200HP3, WG1800HP3, WG1200HS2, WG1900HP, WG1200HP2, W1200EX(-MS), WG1200HS, WG1200HP, WF300HP2, W300P, WF800HP, WR8165N, WG2200HP, WF1200HP2, WG1800HP2, WF1200"
    SOLUTION = "Apply vendor patch for CVE-2024-28005. Upgrade to latest version."
    CVSS_SCORE = 4.7
    SEVERITY = "Medium"
    FAMILY = "General Vulnerability"
    CVE = ['CVE-2024-28005']
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
