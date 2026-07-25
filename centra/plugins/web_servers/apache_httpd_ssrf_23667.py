import asyncio
from plugins import NaslPlugin, PluginResult


class ApacheHttpdSsrf23667Plugin(NaslPlugin):
    PLUGIN_ID = 1372
    NAME = "Apache HTTP Server SSRF via mod_rewrite (CVE-2024-23667)"
    DESCRIPTION = "Apache HTTP Server < 2.4.60 contain a Server-Side Request Forgery vulnerability in mod_rewrite that allows an attacker to make the server send requests to internal systems via specially crafted HTTP headers."
    SOLUTION = "Upgrade Apache HTTP Server to 2.4.60 or later. Review mod_rewrite rules for unsafe redirect patterns."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Servers"
    CVE = ["CVE-2024-23667"]
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /redirect HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"X-Forwarded-Host: evil.com\r\n"
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
                if "Location:" in body and "evil.com" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="Apache SSRF via mod_rewrite - X-Forwarded-Host reflected in Location header",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not vulnerable to Apache SSRF",
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
