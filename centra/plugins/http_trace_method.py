import asyncio
from plugins import NaslPlugin, PluginResult


class HttpTraceMethodPlugin(NaslPlugin):
    PLUGIN_ID = 1377
    NAME = "HTTP TRACE Method Enabled Detection"
    DESCRIPTION = "Detects if the HTTP TRACE method is enabled on web servers. TRACE method can be used for Cross-Site Tracing (XST) attacks to steal HTTP cookies and authentication headers via JavaScript."
    SOLUTION = "Disable the HTTP TRACE method on all production web servers. For Apache: TraceEnable Off. For Nginx: proxy_no_cache or return 405."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"TRACE / HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"X-Test: XST-Test\r\n"
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
                if "HTTP/1.1 200" in body and "X-Test: XST-Test" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} TRACE method enabled on port {p}",
                        solution=self.SOLUTION,
                        evidence="TRACE request returned request headers - XST attack possible",
                        references=["https://owasp.org/www-community/attacks/Cross_Site_Tracing"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"TRACE method disabled on port {p}",
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
