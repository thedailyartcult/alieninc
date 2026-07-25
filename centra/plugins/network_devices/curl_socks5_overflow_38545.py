import asyncio
from plugins import NaslPlugin, PluginResult


class CurlSocks5OverflowPlugin(NaslPlugin):
    PLUGIN_ID = 1345
    NAME = "cURL SOCKS5 Heap Buffer Overflow (CVE-2023-38545)"
    DESCRIPTION = "cURL < 8.4.0 contains a heap-based buffer overflow vulnerability in the SOCKS5 proxy handshake code that can be triggered when a remote server returns an excessively long hostname."
    SOLUTION = "Upgrade cURL to version 8.4.0 or later. Avoid using SOCKS5 proxies with untrusted proxy servers."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Network Devices"
    CVE = ["CVE-2023-38545"]
    PORTS = [1080, 10800]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                socks5_greeting = b"\x05\x01\x00"
                writer.write(socks5_greeting)
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(256), timeout=3)
                writer.close()
                await writer.wait_closed()
                if resp and resp[0] == 5:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} SOCKS5 proxy detected on port {p}",
                        solution=self.SOLUTION,
                        evidence="SOCKS5 proxy service responding to handshake",
                        references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Not a SOCKS5 proxy on port {p}",
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
