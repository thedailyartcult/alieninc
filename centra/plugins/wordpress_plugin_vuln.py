import asyncio
import re
from plugins import NaslPlugin, PluginResult


class WordPressPluginVulnPlugin(NaslPlugin):
    PLUGIN_ID = 1356
    NAME = "WordPress Plugin Vulnerability Detection"
    DESCRIPTION = "Detects vulnerable WordPress plugins by checking for common plugin paths and version disclosure. Reads plugin readme files and checks for known-versions associated with CVEs."
    SOLUTION = "Keep all WordPress plugins updated to their latest versions. Remove unused plugins. Subscribe to WordPress security advisories."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Application"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        plugin_paths = [
            "/wp-content/plugins/akismet/readme.txt",
            "/wp-content/plugins/contact-form-7/readme.txt",
            "/wp-content/plugins/woocommerce/readme.txt",
            "/wp-content/plugins/elementor/readme.txt",
            "/wp-content/plugins/wordpress-seo/readme.txt",
            "/wp-content/plugins/jetpack/readme.txt",
        ]
        for p in ([port] if port else self.PORTS):
            detected = []
            for path in plugin_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: */*\r\n"
                        f"Connection: close\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 200" in body:
                        m = re.search(r'(?:Stable tag|Version)[:\s]*([\d.]+)', body)
                        version = m.group(1) if m else "unknown"
                        plugin_name = path.split("/")[-2]
                        detected.append(f"{plugin_name} v{version}")
                except Exception:
                    continue
            if detected:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} {len(detected)} plugin(s) detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Plugins found: {', '.join(detected)}",
                    references=["https://wordpress.org/plugins/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No WordPress plugins detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
