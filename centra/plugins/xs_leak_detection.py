import asyncio
from plugins import NaslPlugin, PluginResult


class XsLeakDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1347
    NAME = "Cross-Site Search (XS-Leak) Detection"
    DESCRIPTION = "Detects cross-site search vulnerabilities where search results reveal information through response timing, size differences, or status codes. Tests for XS-Leaks via search endpoint comparison."
    SOLUTION = "Implement constant-time responses regardless of search results. Use generic error messages. Consider using same-site cookies and COOP headers."
    CVSS_SCORE = 4.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            search_paths = ["/search?q=", "/api/search?q=", "/?s=", "/search/?q="]
            found = []
            for sp in search_paths:
                responses = {}
                for q in ["a", "b", "admin", "password", "secret", ""]:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        request = (
                            f"GET {sp}{q} HTTP/1.1\r\n"
                            f"Host: {target}:{p}\r\n"
                            f"User-Agent: CentraScanner/1.0\r\n"
                            f"Accept: */*\r\n"
                            f"Connection: close\r\n\r\n"
                        )
                        writer.write(request.encode())
                        await writer.drain()
                        start = asyncio.get_event_loop().time()
                        resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                        elapsed = asyncio.get_event_loop().time() - start
                        writer.close()
                        await writer.wait_closed()
                        body = resp.decode("utf-8", errors="replace")
                        status = ""
                        for line in body.split("\r\n"):
                            if "HTTP/1.1" in line or "HTTP/1.0" in line:
                                status = line
                                break
                        responses[q] = (len(resp), elapsed, status)
                    except Exception:
                        continue
                if len(responses) >= 2:
                    sizes = set(r[0] for r in responses.values())
                    if len(sizes) > 1:
                        found.append(sp)
            if found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Search paths differ in response size on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"XS-Leak vectors: {', '.join(found)}",
                    references=["https://xsleaks.dev/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No XS-Leak detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
