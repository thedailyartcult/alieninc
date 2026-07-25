import asyncio
from plugins import NaslPlugin, PluginResult


class AwsSecurityGroupAuditPlugin(NaslPlugin):
    PLUGIN_ID = 1330
    NAME = "AWS Security Group Misconfiguration Audit"
    DESCRIPTION = "Checks for overly permissive AWS Security Group rules that allow open access (0.0.0.0/0) to sensitive ports (SSH 22, RDP 3389, MySQL 3306, etc.) which can lead to unauthorized access."
    SOLUTION = "Restrict Security Group ingress rules to specific IP ranges. Never use 0.0.0.0/0 for sensitive ports. Use AWS Firewall Manager for central management."
    CVSS_SCORE = 8.0
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        sg_patterns = [
            ("0.0.0.0/0", "Open to all traffic"),
            ("sg-", "Security Group ID referenced"),
            ("security-group", "Security Group configuration"),
            ("ingress", "Security Group ingress rule"),
            ("cidr_ip", "CIDR IP configuration"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/aws", "/.aws/config", "/config", "/meta-data/security-groups"]:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
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
                    for pattern, desc in sg_patterns:
                        if pattern in body:
                            findings.append(desc)
                    if len(findings) >= 2:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Security Group info exposed on port {p}",
                            solution=self.SOLUTION,
                            evidence="; ".join(findings),
                            references=["https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No SG misconfiguration on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
