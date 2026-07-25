import asyncio
from plugins import NaslPlugin, PluginResult


class CspPolicyAnalysisPlugin(NaslPlugin):
    PLUGIN_ID = 1346
    NAME = "CSP Policy Strength Analysis"
    DESCRIPTION = "Analyzes Content-Security-Policy headers for weakness including missing directives, unsafe-eval, unsafe-inline, wildcard origins, and missing object-src or script-src directives."
    SOLUTION = "Implement strict CSP directives. Avoid unsafe-inline and unsafe-eval. Use nonces or hashes for inline scripts. Specify exact script-src origins."
    CVSS_SCORE = 5.0
    SEVERITY = "Medium"
    FAMILY = "Web Security"
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
                csp_header = ""
                for line in body.split("\r\n"):
                    if "content-security-policy" in line.lower():
                        csp_header = line.split(":", 1)[1].strip()
                        break
                if csp_header:
                    weaknesses = []
                    if "unsafe-inline" in csp_header:
                        weaknesses.append("unsafe-inline allowed")
                    if "unsafe-eval" in csp_header:
                        weaknesses.append("unsafe-eval allowed")
                    if "*" in csp_header:
                        weaknesses.append("wildcard origins")
                    if "script-src" not in csp_header and "default-src" not in csp_header:
                        weaknesses.append("missing script-src/default-src")
                    if "object-src" not in csp_header:
                        weaknesses.append("missing object-src")
                    if "base-uri" not in csp_header:
                        weaknesses.append("missing base-uri")
                    if weaknesses:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} {len(weaknesses)} weakness(es) on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"CSP: {csp_header[:200]}. Issues: {'; '.join(weaknesses)}",
                            references=["https://csp.withgoogle.com/docs/strict-csp.html"]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=p,
                            cvss_score=0, severity="Info",
                            description=f"CSP policy is strong on port {p}",
                            solution="", evidence=f"CSP: {csp_header[:200]}", references=[]
                        ))
                else:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=6.0, severity="Medium",
                        description="No Content-Security-Policy header found",
                        solution="Implement a CSP header to prevent XSS and data injection attacks.",
                        evidence="CSP header is missing",
                        references=["https://csp.withgoogle.com/docs/strict-csp.html"]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
