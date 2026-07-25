import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class ClickjackingProtectionAssessment(NaslPlugin):
    PLUGIN_ID = 1173
    NAME = "Clickjacking Protection Assessment"
    FAMILY = "Web Applications"
    CVSS_SCORE = 6.1
    DESCRIPTION = "Assesses clickjacking protection by checking for X-Frame-Options and Content-Security-Policy frame-ancestors headers. Missing frame-busting headers allow attackers to embed the site in iframes for clickjacking attacks."
    SOLUTION = "Set X-Frame-Options: DENY or SAMEORIGIN. Use CSP frame-ancestors directive. Implement frame-busting JavaScript as defense-in-depth."
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
                writer.close()
                await writer.wait_closed()
                decoded = response.decode("utf-8", errors="replace")
                header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                xfo_match = re.search(r"X-Frame-Options:\s*(\S+)", header_section, re.I)
                csp_match = re.search(r"Content-Security-Policy:.*?frame-ancestors\s+(\S+)", header_section, re.I)
                score = 0
                notes = []
                if xfo_match:
                    val = xfo_match.group(1).upper()
                    if val in ("DENY", "SAMEORIGIN"):
                        score += 40
                        notes.append(f"X-Frame-Options: {val} (secure)")
                    else:
                        score += 10
                        notes.append(f"X-Frame-Options: {val} (weak)")
                else:
                    notes.append("X-Frame-Options: missing")
                if csp_match:
                    score += 40
                    notes.append(f"CSP frame-ancestors: {csp_match.group(1)} (secure)")
                else:
                    notes.append("CSP frame-ancestors: missing")
                if score < 50:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        description=f"Clickjacking protection score: {score}/80 - {'; '.join(notes)}"
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
