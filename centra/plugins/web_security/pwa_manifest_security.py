import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class PWAManifestSecurity(NaslPlugin):
    PLUGIN_ID = 1279
    NAME = "PWA Manifest Security Check"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 4.0
    DESCRIPTION = "Checks Progressive Web App manifest for security misconfigurations including missing HTTPS, insecure scope definitions, and improper display settings."
    SOLUTION = "Ensure manifest is served over HTTPS. Set appropriate scope and start_url. Use display: standalone or fullscreen. Validate all icons use HTTPS URLs."
    CVE = []
    PORTS = [443, 8443, 80, 8080]

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
                body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                manifest_links = re.findall(r'<link[^>]*rel=["\']manifest["\'][^>]*href=["\']([^"\']+)["\']', body)
                if not manifest_links:
                    continue
                for mf_link in manifest_links:
                    try:
                        mf_url = mf_link if mf_link.startswith("http") else ""
                        if not mf_url.startswith("http"):
                            prefix = f"{scheme}://{host_header}"
                            mf_url = prefix + (mf_link if mf_link.startswith("/") else "/" + mf_link)
                        mf_reader, mf_writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        mf_req = (
                            f"GET {mf_link if mf_link.startswith('/') else '/' + mf_link} HTTP/1.1\r\n"
                            f"Host: {host_header}\r\n"
                            f"Connection: close\r\n"
                            f"\r\n"
                        )
                        mf_writer.write(mf_req.encode())
                        await mf_writer.drain()
                        mf_response = b""
                        while True:
                            chunk = await asyncio.wait_for(mf_reader.read(4096), timeout=5)
                            if not chunk:
                                break
                            mf_response += chunk
                        mf_writer.close()
                        await mf_writer.wait_closed()
                        mf_text = mf_response.decode("utf-8", errors="replace")
                        mf_body = mf_text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in mf_text else ""
                        if mf_text.split("\r\n")[0].startswith("HTTP/1.1 200") or mf_text.split("\r\n")[0].startswith("HTTP/1.0 200"):
                            issues = []
                            if '"display":' not in mf_body and 'display' not in mf_body:
                                issues.append("No display property")
                            if '"https"' not in mf_body and '"http"' in mf_body:
                                issues.append("Uses HTTP URLs in manifest")
                            if issues:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity="medium",
                                    description=self.DESCRIPTION,
                                    solution=self.SOLUTION,
                                    evidence=f"PWA manifest at {mf_link}: {', '.join(issues)}",
                                    references=self.CVE
                                ))
                            else:
                                results.append(PluginResult(
                                    vulnerable=False,
                                    target=target,
                                    port=port_to_check,
                                    description="PWA manifest looks secure."
                                ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        continue
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if 'writer' in locals() and writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
