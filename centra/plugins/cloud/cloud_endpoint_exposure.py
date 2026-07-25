import asyncio
from plugins import NaslPlugin, PluginResult


class CloudEndpointExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1333
    NAME = "Cloud Service Endpoint Exposure Detection"
    DESCRIPTION = "Detects exposed cloud service endpoints including AWS ELB/ALB, API Gateway, CloudFront, Azure Front Door, GCP Load Balancer, and other cloud-managed endpoints that may leak backend information."
    SOLUTION = "Use WAF and origin access controls. Restrict direct access to backend services. Use CloudFront origin access identity or Azure Front Door private link."
    CVSS_SCORE = 5.0
    SEVERITY = "Medium"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        endpoint_sigs = {
            "AWS ELB": [".elb.amazonaws.com", "aws-elb"],
            "AWS ALB": [".elb.amazonaws.com", "x-amzn-trace-id"],
            "AWS API Gateway": [".execute-api.", "amazonaws.com"],
            "CloudFront": [".cloudfront.net", "x-amz-cf-"],
            "AWS EC2": [".compute.amazonaws.com", "ec2-"],
            "Azure Front Door": [".azurefd.net", "x-azure-ref"],
            "Azure App Service": [".azurewebsites.net", ".azure.com"],
            "GCP LB": ["bc.googleusercontent.com", "google.com"],
            "GCP Cloud Run": [".run.app"],
            "Cloudflare": [".cloudflare.net"],
        }
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
                body = resp.decode("utf-8", errors="replace")
                findings = []
                for svc_name, sigs in endpoint_sigs.items():
                    for sig in sigs:
                        if sig.lower() in body.lower():
                            findings.append(svc_name)
                            break
                if findings:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"Cloud endpoint(s) detected on port {p}: {', '.join(set(findings))}",
                        solution=self.SOLUTION,
                        evidence=f"Cloud service signatures: {', '.join(set(findings))}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No cloud endpoints on port {p}",
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
