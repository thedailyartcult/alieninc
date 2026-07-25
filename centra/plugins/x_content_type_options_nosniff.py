import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class XContentTypeOptionsNosniff(NaslPlugin):
    PLUGIN_ID = 1284
    NAME = "X-Content-Type-Options Nosniff Detection"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 4.0
    DESCRIPTION = "Checks if the target sets the X-Content-Type-Options: nosniff header, which prevents MIME type sniffing by browsers."
    SOLUTION = "Set 'X-Content-Type-Options: nosniff' on all responses. This prevents browsers from interpreting files as a different MIME type than declared."
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
                decoded = response.decode("utf-8", errors="replace")
                header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                xcto_match = re.search(r"X-Content-Type-Options:\s*(.*)", header_section, re.I)
                xcto = xcto_match.group(1).strip() if xcto_match else ""
                if "nosniff" in xcto.lower():
                    results.append(PluginResult(
                        vulnerable=False,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="info",
                        description="X-Content-Type-Options: nosniff is properly set.",
                        solution=self.SOLUTION,
                        evidence="Header present: X-Content-Type-Options: nosniff",
                        references=self.CVE
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"X-Content-Type-Options header not set. Current value: '{xcto or 'not present'}'",
                        references=self.CVE
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if 'writer' in locals() and writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
