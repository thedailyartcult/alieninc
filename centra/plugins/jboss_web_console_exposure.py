import asyncio
from plugins import NaslPlugin, PluginResult


class JbossWebConsolePlugin(NaslPlugin):
    PLUGIN_ID = 1362
    NAME = "JBoss Web Console Exposure Detection"
    DESCRIPTION = "Detects exposed JBoss/WildFly web consoles (jmx-console, admin-console, web-console) that allow unauthenticated access to management interfaces, potentially leading to full server compromise."
    SOLUTION = "Restrict JBoss console access, remove consoles in production, or configure strong authentication."
    CVSS_SCORE = 8.0
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2020-10770"]
    PORTS = [80, 443, 8080, 8443, 9990, 9993]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        jboss_paths = [
            "/jmx-console/", "/admin-console/", "/web-console/",
            "/management/", "/console/", "/management/console",
        ]
        for p in ([port] if port else self.PORTS):
            for path in jboss_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
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
                    if "HTTP/1.1 200" in body and ("JBoss" in body or "WildFly" in body or "JMX" in body or "Management Console" in body):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} JBoss console at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"JBoss console accessible: {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No JBoss console on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
