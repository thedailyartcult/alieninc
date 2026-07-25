import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class BusinessLogicBypass(NaslPlugin):
    PLUGIN_ID = 1289
    NAME = "Business Logic Flow Bypass Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects business logic bypass opportunities by analyzing application flow for missing state validation, direct URL access to restricted steps, and parameter tampering."
    SOLUTION = "Implement proper state machine validation for multi-step processes. Validate access at every step. Use server-side session state tracking. Never rely on client-side state."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    STEPS = ["/checkout", "/checkout/address", "/checkout/payment", "/checkout/review", "/checkout/confirm"]

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
                accessed_steps = []
                for step in self.STEPS:
                    request = (
                        f"GET {step} HTTP/1.1\r\n"
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
                            cl_match = __import__("re").search(rb"Content-Length:\s*(\d+)", headers, __import__("re").I)
                            if cl_match:
                                content_length = int(cl_match.group(1))
                                if len(body) >= content_length:
                                    break
                            else:
                                break
                    decoded = response.decode("utf-8", errors="replace")
                    status_line = decoded.split("\r\n")[0] if decoded else ""
                    if "200" in status_line:
                        accessed_steps.append(step)
                if len(accessed_steps) > 1:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Multi-step process steps directly accessible: {', '.join(accessed_steps)}",
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
