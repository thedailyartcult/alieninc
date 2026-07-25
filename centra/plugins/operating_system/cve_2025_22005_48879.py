import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202522005Plugin(NaslPlugin):
    PLUGIN_ID = 48879
    NAME = "CVE-2025-22005"
    DESCRIPTION = "In the Linux kernel, the following vulnerability has been resolved:  ipv6: Fix memleak of nhc_pcpu_rth_output in fib_check_nh_v6_gw().  fib_check_nh_v6_gw() expects that fib6_nh_init() cleans up every"
    SOLUTION = "Apply vendor patch for CVE-2025-22005."
    CVSS_SCORE = 5.5
    FAMILY = "Operating System"
    CVE = ['CVE-2025-22005']
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
                        evidence="CVE-2025-22005 check", references=['CVE-2025-22005']
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
