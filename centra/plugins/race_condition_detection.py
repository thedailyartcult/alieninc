import asyncio
from plugins import NaslPlugin, PluginResult


class RaceConditionPlugin(NaslPlugin):
    PLUGIN_ID = 1352
    NAME = "Race Condition Detection"
    DESCRIPTION = "Detects time-of-check-to-time-of-use (TOCTOU) race conditions in web applications by sending concurrent requests to the same endpoint and checking for inconsistent responses that indicate race condition vulnerabilities."
    SOLUTION = "Use atomic database transactions, row-level locking, or optimistic concurrency control. Implement idempotency keys for critical operations."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        race_paths = ["/api/coupon/redeem", "/api/vote", "/api/apply", "/api/transfer", "/api/claim", "/checkout"]
        for p in ([port] if port else self.PORTS):
            found = False
            for path in race_paths:
                responses = set()
                async def send_req(idx):
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        body = f'{{"id":{idx}}}'
                        request = (
                            f"POST {path} HTTP/1.1\r\n"
                            f"Host: {target}:{p}\r\n"
                            f"Content-Type: application/json\r\n"
                            f"Content-Length: {len(body)}\r\n"
                            f"User-Agent: CentraScanner/1.0\r\n"
                            f"Connection: close\r\n\r\n"
                            f"{body}"
                        )
                        writer.write(request.encode())
                        await writer.drain()
                        resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                        writer.close()
                        await writer.wait_closed()
                        resp_text = resp.decode("utf-8", errors="replace")
                        status = resp_text.split("\r\n")[0] if resp_text else ""
                        responses.add(f"{status}|{len(resp)}")
                    except Exception:
                        pass
                tasks = [send_req(i) for i in range(5)]
                await asyncio.gather(*tasks)
                if len(responses) > 2:
                    found = True
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} Possible race condition on port {p} via {path}",
                        solution=self.SOLUTION,
                        evidence=f"Concurrent requests produced {len(responses)} distinct responses on {path}",
                        references=["https://portswigger.net/web-security/race-conditions"]
                    ))
                    break
            if not found:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No race conditions detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
