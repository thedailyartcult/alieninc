import asyncio
from plugins import NaslPlugin, PluginResult


class CrlfInjectionPlugin(NaslPlugin):
    PLUGIN_ID = 1349
    NAME = "CRLF Injection Detection"
    DESCRIPTION = "Detects CRLF (Carriage Return Line Feed) injection vulnerabilities by injecting newline sequences into parameters and checking if response splitting or header injection occurs."
    SOLUTION = "Sanitize user input by stripping or encoding CR (%0d) and LF (%0a) characters. Use language-level encoding functions for output."
    CVSS_SCORE = 6.1
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            crlf_payloads = [
                ("/redirect?url=http://evil.com%0d%0aLocation:%20http://evil.com", "URL redirect"),
                ("/log?msg=test%0d%0aX-Injected:%20true", "Header injection"),
                ("/?next=%0d%0aSet-Cookie:%20session=evil", "Cookie injection"),
                ("/api?input=test%0aX-Injected:%20true", "LF-only injection"),
            ]
            found = []
            for path, desc in crlf_payloads:
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
                    if "X-Injected" in body or "Set-Cookie" in body or "evil.com" in body:
                        found.append(f"{desc}")
                except Exception:
                    continue
            if found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} CRLF injection possible on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Vectors: {'; '.join(found)}",
                    references=["https://owasp.org/www-community/attacks/CRLF_Injection"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No CRLF injection on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
