import asyncio
from plugins import NaslPlugin, PluginResult


class CloudLoggingDisabledPlugin(NaslPlugin):
    PLUGIN_ID = 1332
    NAME = "Cloud Audit Logging Disabled Detection"
    DESCRIPTION = "Checks if cloud audit logging and monitoring configurations are exposed in web-accessible files indicating disabled or misconfigured logging (CloudTrail, AWS Config, Azure Monitor, GCP Cloud Logging)."
    SOLUTION = "Enable CloudTrail for all regions and account activities. Enable Azure Monitor diagnostic settings. Enable GCP Cloud Audit Logs. Use centralized log aggregation."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        logging_keywords = [
            "cloudtrail", "aws_cloudtrail", "aws_config",
            "azure_monitor", "diagnostic_settings", "log_analytics",
            "cloud_logging", "stackdriver", "gcp_logging",
            "log_group", "log_stream", "audit_log",
            "s3:PutBucketLogging", "log_bucket", "access_log",
        ]
        disabled_indicators = [
            "disabled", "false", "no", "off", "none", "skip",
            "logging_enabled: false", "audit_logging: false",
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/config", "/terraform", "/terraform.tfstate", "/main.tf", "/cloudformation"]:
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
                    body_lower = body.lower()
                    has_logging_ref = any(sig in body_lower for sig in logging_keywords)
                    is_disabled = any(ind in body_lower for ind in disabled_indicators)
                    if has_logging_ref and is_disabled:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Audit logging disabled in config on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Logging config found disabled in {path}",
                            references=["https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-configure.html"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No logging issues on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
