import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class SequentialIDEnumeration(NaslPlugin):
    PLUGIN_ID = 1290
    NAME = "Sequential ID Enumeration Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Detects sequential or predictable resource identifiers in URLs that could allow attackers to enumerate all resources by iterating IDs."
    SOLUTION = "Use UUIDs or other non-predictable identifiers. Implement proper access control checks on all resources. Use rate limiting on API endpoints. Consider hashids or similar encoding."
    CVE = ["CVE-2024-26213"]
    PORTS = [80, 443, 8080, 8443]

    ID_PATTERNS = ["/user/", "/profile/", "/order/", "/invoice/", "/document/"]

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
                for pattern in self.ID_PATTERNS:
                    request = (
                        f"GET {pattern} HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
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
                    body_text = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    ids = set(re.findall(rf'{re.escape(pattern)}(\d+)', body_text))
                    if len(ids) > 1:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity="medium",
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Sequential IDs detected in {pattern}: {', '.join(sorted(ids)[:5])}",
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
