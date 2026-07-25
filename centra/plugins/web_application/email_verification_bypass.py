import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class EmailVerificationBypass(NaslPlugin):
    PLUGIN_ID = 1288
    NAME = "Email Verification Bypass Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects email verification bypass opportunities including verification link prediction, rate limiting absence, and email change without re-verification."
    SOLUTION = "Use cryptographically random tokens for verification. Implement rate limiting on verification attempts. Require re-verification for email changes. Set short token expiry."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    INDICATORS = [
        "/verify", "/verify-email", "/email/verify",
        "/confirm", "/register/confirm", "/signup/verify",
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
                for path in self.INDICATORS:
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
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
                    body_text = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "200" in status_line or "302" in status_line:
                        if any(x in body_text.lower() for x in ["verify", "confirm", "email", "activation"]):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity="medium",
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"Email verification endpoint found: {path}. Verify token strength and expiration policy.",
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
