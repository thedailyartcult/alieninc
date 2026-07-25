import asyncio
from plugins import NaslPlugin, PluginResult


class AwsKeyExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1326
    NAME = "AWS Key Exposure via Public Resources"
    DESCRIPTION = "Detects exposed AWS access keys, secret keys, and session tokens in publicly accessible web resources, source code, configuration files, and API responses."
    SOLUTION = "Rotate exposed keys immediately. Use AWS IAM roles instead of long-lived keys. Scan repositories and storage for credentials."
    CVSS_SCORE = 8.5
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        patterns = [
            ("AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
            ("ASIA[0-9A-Z]{16}", "AWS Temporary Access Key"),
            ("(?i)aws_secret_access_key\\s*[=:]\\s*['\"]?[A-Za-z0-9/+=]{40}", "AWS Secret Access Key"),
            ("(?i)aws_session_token\\s*[=:]\\s*['\"]?[A-Za-z0-9/+=]{100,}", "AWS Session Token"),
            ("(?i)amazonaws\\.com.*[A-Za-z0-9/+=]{40}", "AWS URL with Key"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/.env", "/config", "/config.json", "/config.yml", "/config.yaml", "/secrets", "/env"]:
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
                    for pattern, desc in patterns:
                        matches = re.findall(pattern, body)
                        if matches:
                            findings.append(f"{desc} in {path}")
                    if findings:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} AWS credentials exposed on port {p}",
                            solution=self.SOLUTION,
                            evidence="; ".join(findings),
                            references=["https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No AWS key exposure detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
