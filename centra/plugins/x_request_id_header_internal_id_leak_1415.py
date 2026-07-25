import asyncio
from plugins import NaslPlugin, PluginResult


class XRequestIdHeaderInternalIdLeakPlugin(NaslPlugin):
    PLUGIN_ID = 1415
    NAME = "X-Request-ID Header Internal ID Leak"
    DESCRIPTION = "Detects  X-Request-ID HTTP response header"
    SOLUTION = "Configure web server to send X-Request-ID header with appropriate value"
    CVSS_SCORE = 1.0
    SEVERITY = "Info"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\\r\\n"
                    f"Host: {target}:{p}\\r\\n"
                    f"User-Agent: CentraScanner/1.0\\r\\n"
                    f"Accept: */*\\r\\n"
                    f"Connection: close\\r\\n\\r\\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                headers_lower = body.lower()
                has_header = "x-request-id" in headers_lower
                if has_header:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Found header: X-Request-ID",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Check passed",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
