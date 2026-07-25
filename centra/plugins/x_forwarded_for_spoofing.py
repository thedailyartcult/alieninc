import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class XForwardedForSpoofing(NaslPlugin):
    PLUGIN_ID = 1292
    NAME = "X-Forwarded-For IP Spoofing Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects applications that trust X-Forwarded-For or similar headers for security decisions, allowing attackers to spoof IP addresses and bypass access controls."
    SOLUTION = "Do not trust X-Forwarded-For headers for security decisions. Use the actual TCP connection IP for access control. If behind a proxy, configure the proxy to strip untrusted headers."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SPOOF_HEADERS = [
        "X-Forwarded-For: 127.0.0.1",
        "X-Real-IP: 127.0.0.1",
        "X-Forwarded-Host: localhost",
        "Client-IP: 127.0.0.1",
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
                for spoof_header in self.SPOOF_HEADERS:
                    request = (
                        f"GET / HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"{spoof_header}\r\n"
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
                            cl_match = __import__("re").search(rb"Content-Length:\s*(\d+)", headers, __import__("re").I)
                            if cl_match:
                                content_length = int(cl_match.group(1))
                                if len(body) >= content_length:
                                    break
                            else:
                                break
                    decoded = response.decode("utf-8", errors="replace")
                    body_text = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "blocked" not in body_text.lower() and "access denied" not in body_text.lower():
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity="medium",
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Application responded without blocking header spoofing: {spoof_header}",
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
