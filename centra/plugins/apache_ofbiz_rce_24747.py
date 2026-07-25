import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheOfbizRce24747Plugin(NaslPlugin):
    PLUGIN_ID = 1375
    NAME = "Apache OFBiz Remote Code Execution (CVE-2024-24747)"
    DESCRIPTION = "Apache OFBiz < 18.12.11 contain a remote code execution vulnerability in the SOAP/REST interface that allows an unauthenticated attacker to execute arbitrary code via crafted XML data."
    SOLUTION = "Upgrade Apache OFBiz to 18.12.11 or later. Disable SOAP/REST interfaces if not needed."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-24747"]
    PORTS = [80, 443, 8080, 8443, 8444]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/webtools/", "/myportal/", "/catalog/", "/partymgr/"]:
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
                    if "OFBiz" in body or "ofbiz" in body.lower() or "Apache OFBiz" in body:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"OFBiz instance detected on port {p} via {path}",
                            references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="OFBiz not detected",
                    solution="", evidence="", references=[]
                ))
        return results
