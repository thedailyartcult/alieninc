import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class HSTSPreloadStatus(NaslPlugin):
    PLUGIN_ID = 1285
    NAME = "HTTP Strict Transport Security Preload Detection"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 4.0
    DESCRIPTION = "Checks if the target sends a proper HSTS header and evaluates readiness for HSTS preload list inclusion."
    SOLUTION = "Set Strict-Transport-Security with max-age at least 31536000 (1 year), includeSubDomains, and preload. Submit to https://hstspreload.org."
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
                hsts_match = re.search(r"Strict-Transport-Security:\s*(.*)", header_section, re.I)
                hsts = hsts_match.group(1).strip() if hsts_match else ""
                if hsts:
                    details = []
                    ma = re.search(r'max-age=(\d+)', hsts)
                    if ma:
                        max_age = int(ma.group(1))
                        if max_age >= 31536000:
                            details.append(f"max-age {max_age} >= 1 year")
                        else:
                            details.append(f"max-age {max_age} < 1 year (requires 31536000)")
                    if "includesubdomains" in hsts.lower():
                        details.append("includeSubDomains present")
                    if "preload" in hsts.lower():
                        details.append("preload ready")
                    ready = all(x in hsts.lower() for x in ["max-age", "includesubdomains", "preload"])
                    severity = "info" if ready else "medium"
                    results.append(PluginResult(
                        vulnerable=not ready,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity=severity,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"HSTS: {hsts}. {'Preload ready!' if ready else ' '.join(details)}",
                        references=self.CVE
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="high",
                        description="HSTS header not set. Site is vulnerable to SSL stripping attacks.",
                        solution=self.SOLUTION,
                        evidence="No Strict-Transport-Security header found.",
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
