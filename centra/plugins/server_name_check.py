import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class ServerNameTechnologyFingerprinting(NaslPlugin):
    PLUGIN_ID = 1171
    NAME = "Server Name/Technology Fingerprinting"
    FAMILY = "Web Applications"
    CVSS_SCORE = 3.7
    DESCRIPTION = "Fingerprints the web server technology and version for informational purposes. Identifies Nginx, Apache, IIS, Python frameworks, and their versions from response signatures."
    SOLUTION = "Remove version banners from server headers. Use generic error pages. Consider using a reverse proxy layer."
    CVE = []
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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                request = (
                    f"GET / HTTP/1.1\r\n"
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
                decoded = response.decode("utf-8", errors="replace")
                header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                server_info = None
                server_match = re.search(r"Server:\s*(\S+)", header_section, re.I)
                if server_match:
                    server_info = server_match.group(1)
                powered_match = re.search(r"X-Powered-By:\s*(\S+)", header_section, re.I)
                if powered_match:
                    server_info = f"{server_info} / {powered_match.group(1)}" if server_info else powered_match.group(1)
                if server_info:
                    results.append(PluginResult(
                        vulnerable=False,
                        target=target,
                        port=port_to_check,
                        description=f"Server fingerprint: {server_info}"
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
