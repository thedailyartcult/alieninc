import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class NginxRequestSplitting24989(NaslPlugin):
    PLUGIN_ID = 1264
    NAME = "Nginx HTTP/2 Request Splitting (CVE-2024-24989)"
    FAMILY = "Web Servers"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Nginx HTTP/2 implementation is vulnerable to request splitting via crafted HTTP/2 sequenced frames, enabling cache poisoning and request smuggling."
    SOLUTION = "Upgrade Nginx to the latest version containing the security fix for CVE-2024-24989."
    CVE = ["CVE-2024-24989"]
    PORTS = [443, 8443, 80, 8080]

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
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {host_header}\r\n"
                    f"Accept: */*\r\n"
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
                server = ""
                for line in headers_part.split("\r\n"):
                    if line.lower().startswith("server:"):
                        server = line.split(":", 1)[1].strip()
                        break
                if "nginx" in server.lower():
                    version = server.lower().replace("nginx/", "").split()[0]
                    try:
                        parts = [int(x) for x in version.split(".") if x.isdigit()]
                    except Exception:
                        parts = []
                    if parts and len(parts) >= 2:
                        if parts[0] == 1 and (parts[1] < 24 or (parts[1] == 24 and (len(parts) < 3 or parts[2] < 2))):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity=self.severity_from_cvss(self.CVSS_SCORE),
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"Nginx {version} may be vulnerable to HTTP/2 request splitting.",
                                references=self.CVE
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=False,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity="info",
                                description="Nginx version check - HTTP/2 request splitting scan.",
                                solution=self.SOLUTION,
                                evidence=f"Nginx {version} detected. Checking vulnerability status.",
                                references=self.CVE
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
