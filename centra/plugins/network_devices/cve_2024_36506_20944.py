import asyncio
from plugins import NaslPlugin, PluginResult


class Cve202436506Plugin(NaslPlugin):
    PLUGIN_ID = 20944
    NAME = "CVE-2024-36506"
    DESCRIPTION = "An improper verification of source of a communication channel vulnerability [CWE-940] in FortiClientEMS 7.4.0, 7.2.0 through 7.2.4, 7.0 all versions, 6.4 all versions may allow a remote attacker to by"
    SOLUTION = "Apply vendor patch for CVE-2024-36506. Upgrade to latest version."
    CVSS_SCORE = 3.7
    FAMILY = "Network Devices"
    CVE = ['CVE-2024-36506']
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
                        evidence="CVE-2024-36506 check — response received",
                        references=['CVE-2024-36506']
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
