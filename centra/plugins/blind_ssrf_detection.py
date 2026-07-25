import asyncio
from plugins import NaslPlugin, PluginResult


class BlindSsrfDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1313
    NAME = "Blind Server-Side Request Forgery Detection"
    DESCRIPTION = "Tests for blind SSRF vulnerabilities by injecting URL parameters that reference internal IP ranges. Detects if the server makes outbound requests to attacker-controlled resources via HTTP redirects or parameter manipulation."
    SOLUTION = "Implement strict URL validation, block access to private IP ranges, use a blocklist/allowlist approach for outbound requests."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            ssrf_paths = [
                "/?url=http://169.254.169.254/latest/meta-data/",
                "/?url=http://127.0.0.1:8080/",
                "/?url=http://10.0.0.1/",
                "/?url=http://172.16.0.1/",
                "/?url=http://192.168.1.1/",
                "/?redirect=http://127.0.0.1/",
                "/?file=http://localhost/",
                "/proxy?url=http://127.0.0.1:22/",
                "/fetch?url=http://169.254.169.254/",
                "/load?path=http://127.0.0.1:3306/",
            ]
            detected = []
            for path in ssrf_paths:
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
                    if "HTTP/1.1 200" in body:
                        for sig in ["meta-data", "ami-id", "security-credentials", "root", "password", "secret"]:
                            if sig in body.lower():
                                detected.append(path)
                                break
                except Exception:
                    continue
            if detected:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Possible SSRF vector detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"SSRF paths with internal data returned: {', '.join(detected)}",
                    references=["https://owasp.org/www-community/attacks/Server_Side_Request_Forgery"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No blind SSRF detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
