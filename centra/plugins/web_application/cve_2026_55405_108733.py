import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202655405Plugin(NaslPlugin):
    PLUGIN_ID = 108733
    NAME = "CVE-2026-55405"
    DESCRIPTION = "LangChain4j is a Java library for building LLM-powered applications on the JVM. Prior to  1.2.1-beta8, 1.5.1-beta11, 1.11.8-beta19, and 1.16.3-beta26, the MariaDB and pgvector embedding stores build m"
    SOLUTION = "Apply vendor patch for CVE-2026-55405."
    CVSS_SCORE = 7.6
    FAMILY = "Web Application"
    CVE = ['CVE-2026-55405']
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
                        evidence="CVE-2026-55405 check", references=['CVE-2026-55405']
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
