import asyncio
from plugins import NaslPlugin, PluginResult


class ClickjackingProtectionPlugin(NaslPlugin):
    PLUGIN_ID = 1310
    NAME = "X-Frame-Options / Clickjacking Protection Check"
    DESCRIPTION = "Checks if the web application sets X-Frame-Options or Content-Security-Policy: frame-ancestors headers to prevent clickjacking attacks. Missing headers make the application vulnerable to UI redressing."
    SOLUTION = "Set X-Frame-Options: DENY or SAMEORIGIN, or CSP: frame-ancestors 'none' or 'self'."
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
                headers = resp.decode("utf-8", errors="replace")
                headers_lower = headers.lower()
                xfo = "x-frame-options" in headers_lower
                csp_frame = "frame-ancestors" in headers_lower
                if xfo or csp_frame:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Clickjacking protection present on port {p}",
                        solution="",
                        evidence=f"Headers found: XFO={'yes' if xfo else 'no'}, CSP frame-ancestors={'yes' if csp_frame else 'no'}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=5.0, severity="Medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="Neither X-Frame-Options nor CSP frame-ancestors header found",
                        references=["https://owasp.org/www-community/attacks/Clickjacking"]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
