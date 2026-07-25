import asyncio
from plugins import NaslPlugin, PluginResult


class DefaultCredentialsCheckPlugin(NaslPlugin):
    PLUGIN_ID = 1312
    NAME = "Default Credentials Detection"
    DESCRIPTION = "Detects common admin panels and default credential paths across popular web applications, frameworks, and CMS platforms. Probes for exposed admin interfaces without authentication checks."
    SOLUTION = "Remove or restrict access to admin panels. Change default credentials immediately. Use strong passwords and MFA."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        admin_paths = [
            "/admin/", "/administrator/", "/wp-admin/", "/admin/login.php",
            "/phpmyadmin/", "/phpPgAdmin/", "/adminer.php", "/console/",
            "/manager/", "/jenkins/", "/actuator/", "/swagger-ui.html",
            "/graphql", "/api/", "/api/v1/", "/api/v2/", "/_admin/",
            "/login/", "/cgi-bin/", "/server-status", "/status",
        ]
        for p in ([port] if port else self.PORTS):
            exposed = []
            for path in admin_paths:
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
                    if "HTTP/1.1 200" in body or "HTTP/1.1 401" in body or "HTTP/1.1 403" in body:
                        if "login" in body.lower() or "password" in body.lower() or "admin" in body.lower() or "HTTP/1.1 200" in body:
                            exposed.append(path)
                except Exception:
                    continue
            if exposed:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Found {len(exposed)} exposed admin paths on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Exposed paths: {', '.join(exposed)}",
                    references=["https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No default admin panels detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
