import asyncio
from plugins import NaslPlugin, PluginResult


class LoadBalancerDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1308
    NAME = "Load Balancer Detection"
    DESCRIPTION = "Detects load balancers and reverse proxies in front of web applications by analyzing response headers, cookies, and behavior. Detects AWS ELB/ALB, GCP LB, HAProxy, Nginx, Traefik, and others."
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
                lb_signatures = {
                    "AWS ELB": ["aws-elb", "x-amzn-requestid"],
                    "AWS ALB": ["x-amzn-trace-id", "x-amzn-requestid"],
                    "GCP LB": ["x-cloud-trace-context", "via: 1.1 google"],
                    "HAProxy": ["x-haproxy", "x-served-by"],
                    "Traefik": ["x-forwarded-proto", "traefik"],
                    "Envoy": ["x-envoy-", "x-request-id"],
                    "Kong": ["kong", "x-kong-"],
                    "Varnish": ["x-varnish", "via: 1.1 varnish"],
                    "Nginx": ["server: nginx", "x-accel-"],
                    "Apache": ["server: apache", "apache"],
                }
                detected = []
                for lb_name, sigs in lb_signatures.items():
                    for sig in sigs:
                        if sig.lower() in headers.lower():
                            detected.append(lb_name)
                            break
                if detected:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Load balancer detected: {', '.join(set(detected))} on port {p}",
                        solution="",
                        evidence=f"LB signatures: {', '.join(set(detected))}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No load balancer detected on port {p}",
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
