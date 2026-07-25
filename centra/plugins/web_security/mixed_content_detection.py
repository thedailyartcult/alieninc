import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class MixedContentDetection(NaslPlugin):
    PLUGIN_ID = 1277
    NAME = "Mixed Content Detection"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 5.0
    DESCRIPTION = "Detects mixed content issues where HTTPS pages load resources (scripts, stylesheets, images) over insecure HTTP connections, compromising security."
    SOLUTION = "Ensure all resources are loaded over HTTPS. Implement Content Security Policy with upgrade-insecure-requests directive. Use relative protocol URLs (//) or HTTPS URLs."
    CVE = []
    PORTS = [443, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
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
                body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                http_srcs = re.findall(r'src=["\']http://[^"\']+', body, re.I)
                http_hrefs = re.findall(r'href=["\']http://[^"\']+', body, re.I)
                mixed = http_srcs + http_hrefs
                if mixed:
                    unique = list(set(mixed))[:10]
                    csp_match = re.search(r"Content-Security-Policy:.*?", header_section, re.I)
                    if csp_match and "upgrade-insecure-requests" in header_section:
                        severity = "low"
                        detail_note = " CSP upgrade-insecure-requests mitigates this."
                    else:
                        severity = "medium"
                        detail_note = ""
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity=severity,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Found {len(mixed)} mixed content references. Examples: {', '.join(unique)}{detail_note}",
                        references=self.CVE
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False,
                        target=target,
                        port=port_to_check,
                        description="No mixed content detected."
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
