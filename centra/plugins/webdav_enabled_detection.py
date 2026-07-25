import asyncio
from plugins import NaslPlugin, PluginResult


class WebdavEnabledPlugin(NaslPlugin):
    PLUGIN_ID = 1376
    NAME = "WebDAV Enabled Detection"
    DESCRIPTION = "Detects Web Distributed Authoring and Versioning (WebDAV) enabled on web servers via OPTIONS and PROPFIND methods. WebDAV allows file upload, modification, and deletion if not properly secured."
    SOLUTION = "Disable WebDAV unless explicitly required. Restrict WebDAV access with authentication. Use HTTPS for all WebDAV connections."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            for method_check in ["OPTIONS", "PROPFIND"]:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"{method_check} / HTTP/1.1\r\n"
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
                    if method_check == "OPTIONS" and "PROPFIND" in body:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} WebDAV enabled on port {p} (PROPFIND in OPTIONS)",
                            solution=self.SOLUTION,
                            evidence="PROPFIND method allowed - WebDAV enabled",
                            references=["https://owasp.org/www-community/attacks/WebDAV"]
                        ))
                        break
                    elif method_check == "PROPFIND" and ("HTTP/1.1 207" in body or "multistatus" in body):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} WebDAV PROPFIND successful on port {p}",
                            solution=self.SOLUTION,
                            evidence="PROPFIND returned 207 Multi-Status",
                            references=["https://owasp.org/www-community/attacks/WebDAV"]
                        ))
                        break
                except Exception:
                    continue
                if results:
                    break
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"WebDAV not detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
