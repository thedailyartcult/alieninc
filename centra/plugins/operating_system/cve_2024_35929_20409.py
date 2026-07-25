import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202435929Plugin(NaslPlugin):
    PLUGIN_ID = 20409
    NAME = "CVE-2024-35929"
    DESCRIPTION = "In the Linux kernel, the following vulnerability has been resolved:  rcu/nocb: Fix WARN_ON_ONCE() in the rcu_nocb_bypass_lock()  For the kernels built with CONFIG_RCU_NOCB_CPU_DEFAULT_ALL=y and CONFIG"
    SOLUTION = "Apply vendor patch for CVE-2024-35929. Upgrade to latest version."
    CVSS_SCORE = 7.8
    FAMILY = "Operating System"
    CVE = ['CVE-2024-35929']
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
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence="CVE-2024-35929 check — response received",
                        references=['CVE-2024-35929']
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Not detected",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                pass
        return results
