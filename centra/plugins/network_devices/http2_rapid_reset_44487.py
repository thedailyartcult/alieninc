import asyncio
from plugins import NaslPlugin, PluginResult


class Http2RapidResetPlugin(NaslPlugin):
    PLUGIN_ID = 1337
    NAME = "HTTP/2 Rapid Reset DDoS (CVE-2023-44487)"
    DESCRIPTION = "HTTP/2 protocol vulnerability allows rapid stream cancellation causing denial of service. Affects HTTP/2 implementations in most web servers, load balancers, and proxies."
    SOLUTION = "Apply vendor patches. Limit HTTP/2 stream reset rate. Disable HTTP/2 if unnecessary. Upgrade to latest versions of nginx, Apache, Envoy, and other proxies."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2023-44487"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        h2_indicators = ["HTTP/2", "h2", "h2c", "upgrade: h2c", "x-http2"]
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"Upgrade: h2c\r\n"
                    f"HTTP2-Settings: AAMAAABkAARAAAAAAAIAAAAA\r\n"
                    f"Connection: Upgrade, HTTP2-Settings\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Accept: */*\r\n"
                    f"\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                h2_support = any(ind in body for ind in h2_indicators) or "101 Switching" in body
                if h2_support:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} HTTP/2 supported on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"HTTP/2 detected on port {p}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"HTTP/2 not detected on port {p}",
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
