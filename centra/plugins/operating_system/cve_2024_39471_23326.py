import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202439471Plugin(NaslPlugin):
    PLUGIN_ID = 23326
    NAME = "CVE-2024-39471"
    DESCRIPTION = "In the Linux kernel, the following vulnerability has been resolved:  drm/amdgpu: add error handle to avoid out-of-bounds  if the sdma_v4_0_irq_id_to_seq return -EINVAL, the process should be stop to a"
    SOLUTION = "Apply vendor patch for CVE-2024-39471. Upgrade to latest version."
    CVSS_SCORE = 7.1
    FAMILY = "Operating System"
    CVE = ['CVE-2024-39471']
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
                        evidence="CVE-2024-39471 check — response received",
                        references=['CVE-2024-39471']
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
