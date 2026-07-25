import asyncio
from plugins import NaslPlugin, PluginResult


class ServerBannerDisclosurePlugin(NaslPlugin):
    PLUGIN_ID = 1379
    NAME = "Server Banner Information Disclosure"
    DESCRIPTION = "Detects verbose server banners in HTTP response headers that disclose detailed version information (Apache/2.4.57, Nginx/1.24.0, etc.), aiding attackers in targeting version-specific vulnerabilities."
    SOLUTION = "Configure web server to show minimal server banner. For Apache: ServerTokens Prod. For Nginx: server_tokens off. For IIS: Remove Server header via URLScan."
    CVSS_SCORE = 3.7
    SEVERITY = "Low"
    FAMILY = "Information Gathering"
    CVE = []
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
                server_header = ""
                powered_by = ""
                for line in body.split("\r\n"):
                    if line.lower().startswith("server:"):
                        server_header = line.split(":", 1)[1].strip()
                    if line.lower().startswith("x-powered-by:"):
                        powered_by = line.split(":", 1)[1].strip()
                if server_header and len(server_header) > 10:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Verbose server banner: '{server_header}' on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Server: {server_header}, X-Powered-By: {powered_by}",
                        references=["https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/"]
                    ))
                elif powered_by:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Technology disclosure via X-Powered-By: '{powered_by}' on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"X-Powered-By: {powered_by}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Minimal server banner on port {p}",
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
