import asyncio
from plugins import NaslPlugin, PluginResult


class CachePoisoningDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1314
    NAME = "Web Cache Poisoning Detection"
    DESCRIPTION = "Detects potential web cache poisoning vulnerabilities by injecting unkeyed headers (X-Forwarded-Host, X-Forwarded-Proto, X-Original-URL) and checking if the response reflects attacker-controlled values in cached responses."
    SOLUTION = "Ensure caches key on all relevant headers. Do not dynamically generate cache keys from user-supplied headers. Use Vary headers appropriately."
    CVSS_SCORE = 6.1
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            cache_indicators = ["x-cache", "cf-cache-status", "x-nginx-cache", "x-proxy-cache", "age:", "cache-control"]
            unkeyed_tests = [
                ("X-Forwarded-Host", "evil.com"),
                ("X-Forwarded-Proto", "https"),
                ("X-Original-URL", "/admin"),
                ("X-Rewrite-URL", "/evil"),
                ("X-HTTP-Method-Override", "PUT"),
            ]
            poisoned = []
            for header_name, header_val in unkeyed_tests:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET / HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"{header_name}: {header_val}\r\n"
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
                    has_cache = any(ind in body.lower() for ind in cache_indicators)
                    reflects = header_val in body
                    if reflects and has_cache:
                        poisoned.append(f"{header_name}: {header_val}")
                except Exception:
                    continue
            if poisoned:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Cache poisoning vector detected on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"Unkeyed headers reflected in cached response: {', '.join(poisoned)}",
                    references=["https://portswigger.net/web-security/web-cache-poisoning"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No cache poisoning detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
