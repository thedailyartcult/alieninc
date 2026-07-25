import asyncio
from plugins import NaslPlugin, PluginResult


class MultiCloudCredentialLeakPlugin(NaslPlugin):
    PLUGIN_ID = 1334
    NAME = "Multi-Cloud Credential Leakage Detection"
    DESCRIPTION = "Detects exposed credentials from multiple cloud providers (AWS, Azure, GCP, DigitalOcean, Heroku, etc.) in public configuration files, source code, and environment dumps."
    SOLUTION = "Use credential scanners in CI/CD pipelines. Store secrets in vaults (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager). Never commit credentials to source control."
    CVSS_SCORE = 9.0
    SEVERITY = "Critical"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        cred_patterns = [
            ("(?i)aws_access_key_id\\s*[=:]\\s*['\"]?AKIA", "AWS Access Key"),
            ("(?i)azure_storage_account_key", "Azure Storage Key"),
            ("(?i)azure_connection_string", "Azure Connection String"),
            ("(?i)GOOGLE_APPLICATION_CREDENTIALS", "GCP Credentials"),
            ("(?i)digitalocean_token", "DigitalOcean Token"),
            ("(?i)heroku_api_key", "Heroku API Key"),
            ("(?i)gitlab_token", "GitLab Token"),
            ("(?i)github_token", "GitHub Token"),
            ("(?i)slack_token|xox[baprs]-", "Slack Token"),
            ("(?i)stripe_api_key|sk_live_|pk_live_", "Stripe Key"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/.env", "/.git/config", "/config.json", "/env", "/config", "/credentials"]:
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
                    for pattern, desc in cred_patterns:
                        if re.search(pattern, body):
                            findings.append(desc)
                    if findings:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Cloud credentials leaked on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Credentials in {path}: {', '.join(findings)}",
                            references=["https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No cloud credentials leaked on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
