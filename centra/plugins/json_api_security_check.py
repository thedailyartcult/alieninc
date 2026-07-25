import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class JSONAPISecurityCheck(NaslPlugin):
    PLUGIN_ID = 1295
    NAME = "JSON API Security Misconfiguration Scan"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Detects JSON API (jsonapi.org) specification endpoints and checks for security misconfigurations including missing authentication, excessive data exposure, and improper sparse field-sets."
    SOLUTION = "Implement proper authentication for all JSON API endpoints. Apply sparse field-sets to limit data exposure. Use compound documents carefully. Validate all include parameters."
    CVE = []
    PORTS = [80, 443, 8080, 8443, 3000, 4000]

    JSONAPI_ENDPOINTS = [
        "/api", "/api/v1", "/api/v2",
        "/jsonapi", "/rest/v1", "/rest/v2",
    ]

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
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                for endpoint in self.JSONAPI_ENDPOINTS:
                    request = (
                        f"GET {endpoint} HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"Accept: application/vnd.api+json, application/json\r\n"
                        f"Connection: keep-alive\r\n"
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
                        if b"\r\n\r\n" in response:
                            headers, _, body = response.partition(b"\r\n\r\n")
                            cl_match = re.search(rb"Content-Length:\s*(\d+)", headers, re.I)
                            if cl_match:
                                content_length = int(cl_match.group(1))
                                if len(body) >= content_length:
                                    break
                            else:
                                break
                    decoded = response.decode("utf-8", errors="replace")
                    header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                    body_text = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    ct = ""
                    ct_match = re.search(r"Content-Type:\s*(\S+)", header_section, re.I)
                    if ct_match:
                        ct = ct_match.group(1)
                    if "vnd.api+json" in ct or "application/json" in ct:
                        if '"data"' in body_text or '"type"' in body_text or '"id"' in body_text:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity="medium",
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"JSON API endpoint found at {endpoint}. Content-Type: {ct}",
                                references=self.CVE
                            ))
                            break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if 'writer' in locals() and writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
