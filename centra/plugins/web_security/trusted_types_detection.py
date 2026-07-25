import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class TrustedTypesDetection(NaslPlugin):
    PLUGIN_ID = 1280
    NAME = "Trusted Types CSP Detection"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 3.7
    DESCRIPTION = "Checks if the target application implements Trusted Types in its Content Security Policy. Trusted Types help prevent DOM-based cross-site scripting attacks by requiring sanitized input for DOM manipulation."
    SOLUTION = "Implement Trusted Types by adding 'require-trusted-types-for \"script\"' to your Content Security Policy header and creating appropriate Trusted Type policies."
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
                csp_match = re.search(r"Content-Security-Policy:\s*(.*)", header_section, re.I)
                csp = csp_match.group(1) if csp_match else ""
                if "require-trusted-types-for" in csp:
                    results.append(PluginResult(
                        vulnerable=False,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="info",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="Trusted Types enforced via CSP: require-trusted-types-for.",
                        references=self.CVE
                    ))
                elif csp:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="Trusted Types not enforced. CSP present but missing require-trusted-types-for directive.",
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
                        evidence="No CSP header found. Trusted Types cannot be enforced.",
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
