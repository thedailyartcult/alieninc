import asyncio
from plugins import NaslPlugin, PluginResult


class ApiMassAssignmentPlugin(NaslPlugin):
    PLUGIN_ID = 1320
    NAME = "API Mass Assignment Vulnerability Detection"
    DESCRIPTION = "Tests for mass assignment vulnerabilities in REST APIs by sending unexpected fields in POST/PUT/PATCH requests. If the server accepts user-supplied fields that should be read-only, it may allow privilege escalation."
    SOLUTION = "Use Data Transfer Objects (DTOs) or explicit field allowlists. Never directly bind user input to model attributes."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        mass_assign_fields = [
            '{"role":"admin","is_admin":true,"is_superuser":true}',
            '{"role":"admin","is_admin":true,"is_superuser":true,"permissions":["*"]}',
            '{"role":"admin","is_admin":true,"is_superuser":true,"is_active":true}',
            '{"role":"admin","is_admin":true,"is_superuser":true,"approved":true}',
        ]
        for p in ([port] if port else self.PORTS):
            accepted = []
            for field in mass_assign_fields:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"POST /api/users HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(field)}\r\n"
                        f"Connection: close\r\n\r\n"
                        f"{field}"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body or "HTTP/1.1 201" in body:
                        accepted.append(field[:50])
                except Exception:
                    continue
            if accepted:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Mass assignment possible on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Accepted priviledged fields: {'; '.join(accepted)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa6-mass-assignment/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No mass assignment detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
