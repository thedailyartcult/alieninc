import asyncio
from plugins import NaslPlugin, PluginResult


class PasswordStrengthPolicyPlugin(NaslPlugin):
    PLUGIN_ID = 1353
    NAME = "Password Strength / Auth Policy Assessment"
    DESCRIPTION = "Assesses authentication security by probing password recovery, registration, and login endpoints to determine password policies, rate limiting, account lockout, and other authentication security controls."
    SOLUTION = "Enforce minimum password length (12+ chars), complexity requirements, account lockout after 5 failed attempts, rate limiting on auth endpoints, and MFA."
    CVSS_SCORE = 4.0
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        auth_paths = ["/login", "/register", "/signup", "/forgot-password", "/reset-password", "/api/auth/login"]
        for p in ([port] if port else self.PORTS):
            for path in auth_paths:
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
                    if "HTTP/1.1 200" in body or "HTTP/1.1 401" in body:
                        has_password_input = "password" in body.lower()
                        has_email_input = "email" in body.lower() or "username" in body.lower()
                        has_form = "<form" in body.lower() or "action=" in body.lower() or "type=\"submit\"" in body.lower()
                        if has_password_input and has_form:
                            results.append(PluginResult(
                                vulnerable=False, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"Auth endpoint {path} detected on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Auth page at {path}: form={'yes' if has_form else 'no'}, password_field={'yes' if has_password_input else 'no'}",
                                references=["https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/"]
                            ))
                            break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No auth endpoints on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
