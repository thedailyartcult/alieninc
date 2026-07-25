import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class DefaultFrameworkErrorPageDetection(NaslPlugin):
    PLUGIN_ID = 1172
    NAME = "Default Framework Error Page Detection"
    FAMILY = "Web Applications"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Detects default/framework error pages that reveal the underlying technology stack. Standard error pages for Nginx, Apache, Python Flask/Django, Node.js Express can identify the server software and version."
    SOLUTION = "Customize error pages for all HTTP status codes. Remove framework-specific branding from error responses."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    ERROR_PATTERNS = [
        ("Nginx", "nginx"),
        ("Apache", "apache"),
        ("Flask", "flask"),
        ("Django", "django"),
        ("Express", "express"),
        ("Node.js", "node"),
        ("Tomcat", "tomcat"),
        ("JBoss", "jboss"),
        ("WebLogic", "weblogic"),
        ("IIS", "iis"),
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        paths = ["/nonexistent12345", "/test123", "/.env", "/admin", "/console"]
        for port_to_check in (self.PORTS if port is None else [port]):
            for path in paths:
                try:
                    scheme = "https" if port_to_check in (443, 8443) else "http"
                    ctx = None
                    if scheme == "https":
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    host_header = target
                    if target in ("127.0.0.1", "localhost", "::1"):
                        host_header = "alieninc.tech"
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
                    writer.close()
                    await writer.wait_closed()
                    decoded = response.decode("utf-8", errors="replace").lower()
                    for tech_name, pattern in self.ERROR_PATTERNS:
                        if pattern in decoded:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                description=f"Default error page detected for {tech_name} at {path}"
                            ))
                            break
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
