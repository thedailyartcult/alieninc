import asyncio
from plugins import NaslPlugin, PluginResult


class ApiIdorDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1321
    NAME = "API IDOR Detection"
    DESCRIPTION = "Tests for Insecure Direct Object References (IDOR) in API endpoints by enumerating sequential IDs in URL paths and checking if unauthorized access to other users' resources is possible."
    SOLUTION = "Implement proper authorization checks for every API endpoint. Use UUIDs instead of sequential IDs. Verify ownership before returning resources."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        id_patterns = [
            "/api/users/{id}", "/api/v1/users/{id}",
            "/api/orders/{id}", "/api/invoices/{id}",
            "/api/profile/{id}", "/api/account/{id}",
        ]
        for p in ([port] if port else self.PORTS):
            idor_found = []
            for pattern in id_patterns:
                for uid in [1, 2, 3, 100, 1000]:
                    path = pattern.replace("{id}", str(uid))
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        request = (
                            f"GET {path} HTTP/1.1\r\n"
                            f"Host: {target}:{p}\r\n"
                            f"User-Agent: CentraScanner/1.0\r\n"
                            f"Accept: application/json\r\n"
                            f"Connection: close\r\n\r\n"
                        )
                        writer.write(request.encode())
                        await writer.drain()
                        resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                        writer.close()
                        await writer.wait_closed()
                        body = resp.decode("utf-8", errors="replace")
                        if "HTTP/1.1 200" in body and any(sig in body for sig in ['"email"', '"name"', '"id"', '"role"', '"data"']):
                            idor_found.append(path)
                            break
                    except Exception:
                        continue
            if idor_found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} IDOR vulnerability detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Accessible resources: {', '.join(idor_found)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No IDOR detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
