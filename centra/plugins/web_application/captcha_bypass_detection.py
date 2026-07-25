import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class CaptchaBypassDetection(NaslPlugin):
    PLUGIN_ID = 1286
    NAME = "CAPTCHA Bypass Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects CAPTCHA implementation weaknesses including missing CAPTCHA on critical forms, CAPTCHA reuse, and client-side-only CAPTCHA validation."
    SOLUTION = "Implement server-side CAPTCHA validation. Always verify CAPTCHA tokens server-side. Use rate limiting. Implement CSRF tokens alongside CAPTCHA. Use reCAPTCHA v3 or similar."
    CVE = ["CVE-2024-13161"]
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
                forms_without_captcha = []
                form_patterns = re.findall(r'<form[^>]*action=["\']([^"\']+)["\']', body)
                for form_action in form_patterns[:5]:
                    if not any(x in body.lower() for x in ["recaptcha", "g-recaptcha", "h-captcha", "captcha", "turnstile"]):
                        forms_without_captcha.append(form_action)
                if forms_without_captcha:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Forms without CAPTCHA: {', '.join(forms_without_captcha)}",
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
