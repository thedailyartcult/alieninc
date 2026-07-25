import asyncio
from plugins import NaslPlugin, PluginResult


class OauthTokenLeakagePlugin(NaslPlugin):
    PLUGIN_ID = 1318
    NAME = "OAuth Token Leakage via Referer Header"
    DESCRIPTION = "Checks if OAuth tokens or authorization codes are leaked via the Referer header when the application loads external resources (images, scripts, CSS) from third-party origins."
    SOLUTION = "Use Referrer-Policy header to prevent leakage. Use state parameter with PKCE for OAuth flows. Avoid including tokens in URL query parameters."
    CVSS_SCORE = 6.1
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443]

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
                ref_policy = None
                for line in body.split("\r\n"):
                    if "referrer-policy" in line.lower():
                        ref_policy = line
                has_third_party = any(dom in body for dom in [
                    "http://", "src=", "href=", "//cdn.", "//fonts.", "//analytics."
                ])
                if ref_policy and ("unsafe-url" in ref_policy.lower() or "no-referrer-when-downgrade" in ref_policy.lower()):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Weak referrer policy allows OAuth token leakage",
                        solution=self.SOLUTION,
                        evidence=f"Referrer-Policy: {ref_policy}. Third-party resources: {has_third_party}",
                        references=["https://portswigger.net/web-security/oauth"]
                    ))
                elif not ref_policy and has_third_party:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=5.0, severity="Medium",
                        description="No Referrer-Policy set with third-party resources present",
                        solution=self.SOLUTION,
                        evidence="Missing Referrer-Policy header with third-party resources on page",
                        references=["https://portswigger.net/web-security/oauth"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"OAuth token leakage risk low on port {p}",
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
