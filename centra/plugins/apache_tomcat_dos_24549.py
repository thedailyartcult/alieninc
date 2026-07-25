import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheTomcatDos24549Plugin(NaslPlugin):
    PLUGIN_ID = 1370
    NAME = "Apache Tomcat Denial of Service (CVE-2024-24549)"
    DESCRIPTION = "Apache Tomcat < 9.0.89, 10.1.25, 11.0.0-M16 contain a denial of service vulnerability in the HTTP/2 multiplexing that allows an attacker to cause excessive resource consumption via crafted stream IDs."
    SOLUTION = "Upgrade Apache Tomcat to 9.0.89, 10.1.25, 11.0.0-M16 or later."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-24549"]
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
                if "Apache Tomcat" in body or "Apache-Coyote" in body or "tomcat" in body.lower():
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Apache Tomcat detected on port {p}: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Apache Tomcat not detected",
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
