import asyncio
from plugins import NaslPlugin, PluginResult


class ApiErrorDisclosurePlugin(NaslPlugin):
    PLUGIN_ID = 1319
    NAME = "API Error Message Information Disclosure"
    DESCRIPTION = "Detects if API endpoints leak sensitive information in error responses such as stack traces, database errors, internal paths, or configuration details."
    SOLUTION = "Implement generic error messages in production. Log detailed errors server-side but return sanitized responses to clients."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        error_triggers = [
            "/api/nonexistent", "/api/v1/../../etc/passwd",
            "/api/undefined", "/api/%00", "/api/null",
            "/api/test'", '/api/test"', "/api/<script>",
        ]
        leak_indicators = [
            "Traceback", "Stack trace", "at ", "SyntaxError",
            "File \"", "line ", "mysql_error", "SQL syntax",
            "PDOException", "NullPointerException", "RuntimeException",
            "java.lang", "django", "flask", "werkzeug",
            "/var/www", "/home/", "C:\\", "root:", "internal",
        ]
        for p in ([port] if port else self.PORTS):
            leaks = []
            for path in error_triggers:
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
                    resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    for ind in leak_indicators:
                        if ind.lower() in body.lower():
                            leaks.append(f"{path}:{ind}")
                            break
                except Exception:
                    continue
            if leaks:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} {len(leaks)} information leaks detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Leaks found: {'; '.join(leaks[:10])}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No API error disclosure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
