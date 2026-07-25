import asyncio
from plugins import NaslPlugin, PluginResult


class IvantiXxePlugin(NaslPlugin):
    PLUGIN_ID = 1342
    NAME = "Ivanti Connect Secure XXE (CVE-2024-22024)"
    DESCRIPTION = "Ivanti Connect Secure (ICS) versions before 9.1R18.5, 22.4R2.4, 22.5R1.2 contain an XML External Entity (XXE) vulnerability in the SAML component that allows an unauthenticated attacker to read arbitrary files on the server."
    SOLUTION = "Apply Ivanti patches per advisory. Upgrade to 9.1R18.5, 22.4R2.4, or 22.5R1.2. Disable SAML SSO if not needed."
    CVSS_SCORE = 8.3
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-22024"]
    PORTS = [443, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /dana-na/auth/saml-login.cgi HTTP/1.1\r\n"
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
                if "SAML" in body or "saml" in body or "Ivanti" in body or "Pulse" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Ivanti SAML endpoint detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"SAML login page: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Ivanti SAML not detected on port {p}",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
