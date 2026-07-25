import asyncio
from plugins import NaslPlugin, PluginResult


class HttpParameterPollutionPlugin(NaslPlugin):
    PLUGIN_ID = 1348
    NAME = "HTTP Parameter Pollution Detection"
    DESCRIPTION = "Detects HTTP parameter pollution vulnerabilities where duplicate or conflicting HTTP parameters are handled inconsistently, potentially allowing authentication bypass or input validation bypass."
    SOLUTION = "Use consistent parameter parsing. Reject requests with duplicate parameters. Validate all parameters against strict allowlists."
    CVSS_SCORE = 5.0
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            hpp_tests = [
                "/?admin=false&admin=true",
                "/?auth=false&auth=true",
                "/?authenticated=no&authenticated=yes",
                "/?role=user&role=admin",
                "/?access=deny&access=allow",
                "/api/admin?authorized=false&authorized=true",
            ]
            found = []
            for path in hpp_tests:
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
                    if "HTTP/1.1 200" in body and any(sig in body.lower() for sig in ["admin", "true", "authorized", "allow"]):
                        found.append(path)
                except Exception:
                    continue
            if found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Parameter pollution vector on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"HPP test paths: {', '.join(found)}",
                    references=["https://owasp.org/www-community/attacks/HTTP_Parameter_Pollution"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No HPP detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
