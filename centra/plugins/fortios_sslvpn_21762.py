import asyncio
from plugins import NaslPlugin, PluginResult


class FortiOSVpnPlugin(NaslPlugin):
    PLUGIN_ID = 1340
    NAME = "FortiOS SSL VPN RCE (CVE-2024-21762)"
    DESCRIPTION = "FortiOS < 7.6.0 contains a heap-based buffer overflow vulnerability in the SSL VPN component that allows an unauthenticated attacker to execute arbitrary code via specially crafted requests."
    SOLUTION = "Upgrade FortiOS to version 7.6.0, 7.4.4, 7.2.8, 7.0.15 or later. Apply Fortinet security advisory FG-IR-24-025."
    CVSS_SCORE = 9.8
    SEVERITY = "Critical"
    FAMILY = "Network Devices"
    CVE = ["CVE-2024-21762"]
    PORTS = [443, 8443, 10443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET /remote/login HTTP/1.1\r\n"
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
                if "FortiGate" in body or "Fortinet" in body or "SSL VPN" in body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} FortiGate SSL VPN detected on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"FortiGate SSL VPN response: {body[:200]}",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Not a FortiGate SSL VPN on port {p}",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
