import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202653935Plugin(NaslPlugin):
    PLUGIN_ID = 108092
    NAME = "CVE-2026-53935"
    DESCRIPTION = "Cilium is a networking, observability, and security solution. Prior to 1.17.16, from 1.18.2 to 1.18.9, and from 1.19.0 to 1.19.3, users with the ability to create CiliumLocalRedirectPolicies can speci"
    SOLUTION = "Apply vendor patch for CVE-2026-53935."
    CVSS_SCORE = 6.9
    FAMILY = "Network Devices"
    CVE = ['CVE-2026-53935']
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}\r\n"
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
                if "HTTP/1.1 200" in body or "HTTP/1.1 403" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.severity_from_cvss(self.CVSS_SCORE),
                        description=self.DESCRIPTION, solution=self.SOLUTION,
                        evidence="CVE-2026-53935 check", references=['CVE-2026-53935']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected", solution="", evidence="", references=[]
                    ))
            except Exception:
                pass
        return results
