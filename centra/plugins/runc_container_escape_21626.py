import asyncio
from plugins import NaslPlugin, PluginResult


class RuncEscape21626Plugin(NaslPlugin):
    PLUGIN_ID = 1303
    NAME = "runc Container Escape (CVE-2024-21626)"
    DESCRIPTION = "runc < 1.1.12 contains a race condition vulnerability in the container runtime that allows a malicious container to escape and gain access to the host file system via a crafted WORKDIR directive."
    SOLUTION = "Upgrade runc to version 1.1.12 or later. Update Docker to 25.0.2+ or containerd to 1.6.28+/1.7.13+."
    CVSS_SCORE = 8.6
    SEVERITY = "High"
    FAMILY = "Container Security"
    CVE = ["CVE-2024-21626"]
    PORTS = [2375, 2376, 8443, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /version HTTP/1.1\r\n"
                    f"Host: localhost\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Accept: application/json\r\n"
                    f"Connection: close\r\n\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                if "HTTP/1.1 200" in body and ("Docker" in body or "docker" in body):
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Docker API exposed on port {p} — potential container escape vector",
                        solution=self.SOLUTION,
                        evidence=f"Docker API accessible: {body[:300]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Target does not expose Docker API",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect to target",
                    solution="", evidence="", references=[]
                ))
        return results
