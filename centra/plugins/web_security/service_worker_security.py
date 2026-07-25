import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class ServiceWorkerSecurity(NaslPlugin):
    PLUGIN_ID = 1278
    NAME = "Service Worker Security Audit"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 6.1
    DESCRIPTION = "Checks if the target uses service workers and evaluates their security posture. Insecure service workers can be hijacked to intercept all network requests from the origin."
    SOLUTION = "Register service workers only over HTTPS. Use strict scope restrictions. Validate all messages passed to service workers. Avoid using service workers for sensitive operations without proper authentication."
    CVE = []
    PORTS = [443, 8443, 80, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        sw_patterns = [
            "navigator.serviceWorker", "serviceWorker.register",
            "serviceworker", "sw.js", "service-worker.js",
        ]
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
                body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                matches = [p for p in sw_patterns if p in body.lower()]
                if matches:
                    sw_urls = re.findall(r"(?:register\('|\")([^'\"\s]+(?:sw\.js|service-worker[^'\"\s]*))", body)
                    detail = f"Service worker usage detected. Patterns: {', '.join(matches)}"
                    if sw_urls:
                        detail += f". SW URLs: {', '.join(sw_urls)}"
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=detail,
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
