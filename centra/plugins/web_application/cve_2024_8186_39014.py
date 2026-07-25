import asyncio
from plugins import NaslPlugin, PluginResult


class Cve20248186Plugin(NaslPlugin):
    PLUGIN_ID = 39014
    NAME = "CVE-2024-8186"
    DESCRIPTION = "An issue has been discovered in GitLab CE/EE affecting all versions from 16.6 before 17.7.6, 17.8 before 17.8.4, and 17.9 before 17.9.1. An attacker could inject HMTL into the child item search potent"
    SOLUTION = "Apply vendor patch for CVE-2024-8186."
    CVSS_SCORE = 5.4
    FAMILY = "Web Application"
    CVE = ['CVE-2024-8186']
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
                        evidence="CVE-2024-8186 check", references=['CVE-2024-8186']
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
