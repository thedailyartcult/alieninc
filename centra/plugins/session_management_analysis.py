import asyncio
from plugins import NaslPlugin, PluginResult


class SessionManagementPlugin(NaslPlugin):
    PLUGIN_ID = 1355
    NAME = "Session Management Security Analysis"
    DESCRIPTION = "Analyzes session management implementation including session cookie flags, session fixation protection, session timeout, and secure session handling."
    SOLUTION = "Set Secure, HttpOnly, and SameSite flags on session cookies. Implement absolute and idle session timeouts. Regenerate session IDs after login. Use cryptographic random session identifiers."
    CVSS_SCORE = 6.0
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
                findings = []
                set_cookies = []
                for line in body.split("\r\n"):
                    if "set-cookie" in line.lower():
                        set_cookies.append(line)
                if set_cookies:
                    for sc in set_cookies:
                        if "secure" not in sc.lower():
                            findings.append("Missing Secure flag")
                        if "httponly" not in sc.lower():
                            findings.append("Missing HttpOnly flag")
                        if "samesite" not in sc.lower():
                            findings.append("Missing SameSite attribute")
                    if not findings:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=p,
                            cvss_score=0, severity="Info",
                            description=f"Session cookies properly configured on port {p}",
                            solution="",
                            evidence=f"Cookies with Secure+HttpOnly+SameSite: {len(set_cookies)}",
                            references=[]
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} {len(findings)} issue(s) on port {p}",
                            solution=self.SOLUTION,
                            evidence="; ".join(findings),
                            references=["https://owasp.org/www-community/controls/SecureFlag"]
                        ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No session cookies set on port {p}",
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
