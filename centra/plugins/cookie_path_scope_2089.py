import asyncio
from plugins import NaslPlugin, PluginResult


class CookiePathScopePlugin(NaslPlugin):
    PLUGIN_ID = 2089
    NAME = "Cookie Path Scope"
    DESCRIPTION = "Cookie Path Scope Check"
    SOLUTION = "Configure web server to send appropriate security headers."
    CVSS_SCORE = 2.0
    SEVERITY = "Low"
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
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {target}:{p}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                found_cookies = []
                for line in body.split("\\r\\n"):
                    if "set-cookie" in line.lower():
                        found_cookies.append(line)
                missing_flags = []
                if found_cookies:
                    for sc in found_cookies:
                        if "secure" not in sc.lower():
                            missing_flags.append("Secure")
                        if "httponly" not in sc.lower():
                            missing_flags.append("HttpOnly")
                        if "samesite" not in sc.lower():
                            missing_flags.append("SameSite")
                if missing_flags:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Missing flags: {', '.join(missing_flags)}",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Cookies properly configured",
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
