import asyncio
from plugins import NaslPlugin, PluginResult


class TomcatManagerExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1361
    NAME = "Apache Tomcat Manager Exposure Detection"
    DESCRIPTION = "Detects exposed Apache Tomcat manager interfaces (manager/html, manager/status) that allow deployment of malicious web applications or server status monitoring without proper authentication."
    SOLUTION = "Restrict Tomcat manager access to localhost, use strong authentication, or remove the manager applications in production."
    CVSS_SCORE = 8.0
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2020-1935"]
    PORTS = [80, 443, 8080, 8443, 8000]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        manager_paths = [
            "/manager/html", "/manager/status", "/manager/", "/host-manager/",
            "/manager/status?full=true",
        ]
        for p in ([port] if port else self.PORTS):
            for path in manager_paths:
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
                    if "HTTP/1.1 200" in body or "HTTP/1.1 401" in body:
                        if "Tomcat" in body or "Tomcat Manager" in body or "Server status" in body:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} Tomcat manager at {path} on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Tomcat manager accessible: {path}",
                                references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                            ))
                            break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No Tomcat manager on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
