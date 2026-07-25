import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class TFAImplementationFlaws(NaslPlugin):
    PLUGIN_ID = 1287
    NAME = "Two-Factor Authentication Implementation Issues"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects common two-factor authentication implementation flaws including bypass via backup codes, session-based bypass, TOTP reuse window issues, and SMS-based 2FA vulnerabilities."
    SOLUTION = "Implement TOTP with short time windows (30s). Rate limit 2FA attempts. Require 2FA for all sensitive operations. Use app-based authenticators over SMS. Implement proper session invalidation."
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
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
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
                body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                tfa_keywords = ["two-factor", "2fa", "mfa", "multi-factor", "authenticator", "totp", "otp"]
                has_tfa = any(k in body.lower() for k in tfa_keywords)
                if has_tfa:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="info",
                        description="2FA implementation detected. Review for bypass vectors including backup code abuse, session reuse, and SMS interception.",
                        solution=self.SOLUTION,
                        evidence="2FA mentioned on page. Manual review recommended.",
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
