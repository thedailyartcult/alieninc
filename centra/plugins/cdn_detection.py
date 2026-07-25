import asyncio
from plugins import NaslPlugin, PluginResult


class CdnDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1307
    NAME = "Content Delivery Network Detection"
    DESCRIPTION = "Identifies the Content Delivery Network (CDN) in use by analyzing HTTP response headers and DNS behavior. Detects CloudFront, Akamai, Fastly, Cloudflare, KeyCDN, StackPath, and others."
    SOLUTION = "No remediation needed; informational check."
    CVSS_SCORE = 0
    SEVERITY = "Info"
    FAMILY = "Information Gathering"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
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
                headers = resp.decode("utf-8", errors="replace")
                cdn_signatures = {
                    "CloudFront": ["x-amz-cf-id", "x-amz-cf-pop", "CloudFront"],
                    "Cloudflare": ["cf-ray", "__cfduid", "cf-cache-status"],
                    "Akamai": ["x-akamai", "akamai-", "X-Akamai"],
                    "Fastly": ["x-fastly-", "Fastly-SSL", "X-Served-By"],
                    "KeyCDN": ["x-keycdn", "KeyCDN"],
                    "StackPath": ["stackpath", "StackPath"],
                    "Azure CDN": ["x-azure-ref", "AzureCDN"],
                    "GCP CDN": ["x-cloud-trace-context", "google-cloud-cdn"],
                    "CacheFly": ["x-cachefly", "CacheFly"],
                }
                detected = []
                for cdn_name, sigs in cdn_signatures.items():
                    for sig in sigs:
                        if sig.lower() in headers.lower():
                            detected.append(cdn_name)
                            break
                if detected:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"CDN detected: {', '.join(set(detected))} on port {p}",
                        solution="",
                        evidence=f"CDN signatures: {', '.join(set(detected))}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No known CDN detected on port {p}",
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
