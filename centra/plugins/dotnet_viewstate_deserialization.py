import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class DotNetViewStateDeserialization(NaslPlugin):
    PLUGIN_ID = 1263
    NAME = ".NET ViewState Deserialization RCE"
    FAMILY = "Web Frameworks"
    CVSS_SCORE = 9.8
    DESCRIPTION = "ASP.NET Web Forms applications with ViewState using DES or 3DES encryption may be vulnerable to remote code execution via deserialization of malformed ViewState data, allowing an unauthenticated attacker to execute arbitrary commands."
    SOLUTION = "Upgrade .NET Framework to apply security patches. Use AES encryption for ViewState. Enable ViewStateMac with a strong validation key. Configure <machineKey> with SHA1/ASP.NET 4.5+ compatible settings."
    CVE = ["CVE-2023-24904"]
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
                indicators = [
                    "/", "/default.aspx", "/webform.aspx", "/login.aspx", "/index.aspx"
                ]
                for indicator in indicators:
                    request = (
                        f"GET {indicator} HTTP/1.1\r\n"
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
                    body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "__VIEWSTATE" in body:
                        vs_match = re.search(r'__VIEWSTATE" value="([^"]+)"', body)
                        if vs_match:
                            vs_data = vs_match.group(1)
                            details = f"ASP.NET ViewState found at {indicator}. Length: {len(vs_data)} chars."
                            for line in headers_part.split("\r\n"):
                                if line.lower().startswith("x-aspnet-version:") or (line.lower().startswith("x-powered-by:") and "asp.net" in line.lower()):
                                    details += " ASP.NET version exposed in headers."
                                    break
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity=self.severity_from_cvss(self.CVSS_SCORE),
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=details,
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
