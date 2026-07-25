import asyncio
from plugins import NaslPlugin, PluginResult


class GcpIamMisconfigPlugin(NaslPlugin):
    PLUGIN_ID = 1328
    NAME = "GCP IAM Misconfiguration Detection"
    DESCRIPTION = "Detects GCP IAM misconfigurations including overly permissive roles, publicly accessible cloud resources, and service account key exposure in web-accessible files."
    SOLUTION = "Follow least privilege principle for IAM roles. Use workload identity federation instead of service account keys. Regularly audit IAM policies."
    CVSS_SCORE = 8.0
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        gcp_patterns = [
            ("googleusercontent.com", "GCP resource"),
            ("cloudfunctions.net", "Cloud Function"),
            ("appspot.com", "App Engine"),
            ("storage.googleapis.com", "Cloud Storage"),
            ("compute.googleapis.com", "Compute Engine"),
            ("run.app", "Cloud Run"),
            ("(?i)gcp_service_account", "Service Account Key"),
            ("(?i)google_application_credentials", "Application Credentials"),
            ("GOOGLE_CREDENTIALS", "GCP Credentials"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/.env", "/config", "/config.json", "/credentials", "/key.json"]:
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
                    resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    import re
                    findings = []
                    for pattern, desc in gcp_patterns:
                        if re.search(pattern, body, re.IGNORECASE):
                            findings.append(f"{desc} in {path}")
                    if findings:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} GCP resources exposed on port {p}",
                            solution=self.SOLUTION,
                            evidence="; ".join(findings),
                            references=["https://cloud.google.com/iam/docs/best-practices"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No GCP IAM issues on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
