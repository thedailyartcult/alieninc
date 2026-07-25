import asyncio
from plugins import NaslPlugin, PluginResult


class ReverseProxyDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1309
    NAME = "Reverse Proxy Detection"
    DESCRIPTION = "Detects reverse proxies in front of web applications by analyzing HTTP headers, server banners, and request behavior. Identifies Nginx, Apache mod_proxy, Envoy, Traefik, Caddy, IIS ARR, and Squid."
    SOLUTION = "No remediation needed; informational check. Ensure reverse proxy is properly configured to not leak backend information."
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
                proxy_signatures = {
                    "Nginx": ["server: nginx", "nginx"],
                    "Apache mod_proxy": ["via: 1.1 apache", "server: apache"],
                    "Envoy": ["x-envoy-", ":authority"],
                    "Traefik": ["x-forwarded-proto", "traefik"],
                    "Caddy": ["server: caddy", "caddy"],
                    "IIS ARR": ["x-arr-log-id", "arr-"],
                    "Squid": ["x-squid", "squid"],
                    "HAProxy": ["x-served-by", "haproxy"],
                }
                detected = []
                for proxy_name, sigs in proxy_signatures.items():
                    for sig in sigs:
                        if sig.lower() in headers.lower():
                            detected.append(proxy_name)
                            break
                if detected:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Reverse proxy detected: {', '.join(set(detected))} on port {p}",
                        solution="",
                        evidence=f"Proxy signatures: {', '.join(set(detected))}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No reverse proxy detected on port {p}",
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
