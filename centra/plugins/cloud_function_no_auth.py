import asyncio
from plugins import NaslPlugin, PluginResult


class CloudFunctionNoAuthPlugin(NaslPlugin):
    PLUGIN_ID = 1335
    NAME = "Cloud Function Invocation Without Authentication"
    DESCRIPTION = "Detects cloud functions that can be invoked without authentication including AWS Lambda function URLs, GCP Cloud Functions, and Azure Functions configured for anonymous access."
    SOLUTION = "Enable function-level authentication. Use API Gateway with auth for Lambda. Use IAM-based access control for cloud functions."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        func_patterns = [
            ("lambda-url", "Lambda Function URL"),
            ("cloudfunctions.net", "GCP Cloud Function"),
            ("azurewebsites.net/api", "Azure Function"),
            ("azure-api.net", "Azure API"),
            ("amazonaws.com/prod", "API Gateway (prod)"),
            ("amazonaws.com/dev", "API Gateway (dev)"),
            ("amazonaws.com/staging", "API Gateway (staging)"),
            ("netlify/functions", "Netlify Function"),
            ("vercel.app/api", "Vercel Serverless"),
            ("run.app", "Cloud Run"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/api/", "/functions/", "/api/v1/", "/api/v2/", "/"]:
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
                    for sig, desc in func_patterns:
                        if sig.lower() in body.lower():
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} {desc} detected on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Cloud function pattern '{sig}' found in {path}",
                                references=["https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html"]
                            ))
                            break
                    else:
                        continue
                    break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No cloud function exposure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
