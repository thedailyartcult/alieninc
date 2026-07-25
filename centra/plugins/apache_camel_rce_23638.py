import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheCamelRce23638Plugin(NaslPlugin):
    PLUGIN_ID = 1368
    NAME = "Apache Camel Remote Code Execution (CVE-2024-23638)"
    DESCRIPTION = "Apache Camel < 4.0.4, 3.21.4, 3.14.10 contain a deserialization vulnerability in the default TypeConverter that allows an attacker to execute arbitrary code via crafted HTTP headers."
    SOLUTION = "Upgrade Apache Camel to 4.0.4, 3.21.4, 3.14.10 or later."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-23638"]
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
                    f"CamelHttpMethod: POST\r\n"
                    f"CamelHttpPath: /test\r\n"
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
                if "camel" in body.lower() or "Apache Camel" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Apache Camel detected: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Apache Camel not detected",
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
