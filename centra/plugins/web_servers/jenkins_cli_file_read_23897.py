import asyncio
from plugins import NaslPlugin, PluginResult


class JenkinsCliFileReadPlugin(NaslPlugin):
    PLUGIN_ID = 1297
    NAME = "Jenkins CLI Arbitrary File Read"
    DESCRIPTION = "Jenkins <= 2.441, LTS <= 2.426.3 contains an arbitrary file read vulnerability in the CLI command parser that allows unauthenticated attackers to read arbitrary files from the file system."
    SOLUTION = "Upgrade Jenkins to version 2.442 or LTS 2.426.4 or later."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-23897"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /cli?remoting=false HTTP/1.1\r\n"
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
                if "HTTP/1.1 200" in body and ("Jenkins-CLI" in body or "CLI" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Jenkins CLI endpoint exposed on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Jenkins CLI endpoint accessible: {body[:500]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target not vulnerable to Jenkins CLI file read",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect to target",
                    solution="", evidence="", references=[]
                ))
        return results
