import asyncio
from plugins import NaslPlugin, PluginResult


class CrossDomainPolicyExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1383
    NAME = "Cross-Domain Policy File Exposure"
    DESCRIPTION = "Detects exposed cross-domain policy files (crossdomain.xml, clientaccesspolicy.xml) that allow Flash, Silverlight, or other browser plugins to make cross-origin requests, potentially bypassing same-origin policy."
    SOLUTION = "Remove cross-domain policy files if not needed. Restrict allowed domains to specific trusted origins. Do not use wildcard (*) allow-access entries."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        policy_paths = [
            "/crossdomain.xml", "/clientaccesspolicy.xml",
            "/flash/crossdomain.xml", "/crossdomain.xml",
        ]
        for p in ([port] if port else self.PORTS):
            for path in policy_paths:
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
                    if "HTTP/1.1 200" in body:
                        has_wildcard = "*" in body
                        is_policy = "cross-domain" in body.lower() or "allow-access-from" in body or "access-policy" in body
                        if is_policy:
                            severity = self.CVSS_SCORE if has_wildcard else 4.0
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=severity, severity="Medium" if severity == 4.0 else "Medium",
                                description=f"{self.DESCRIPTION} Policy file at {path} on port {p}" + (" (wildcard)" if has_wildcard else ""),
                                solution=self.SOLUTION,
                                evidence=f"Policy file: {path}, wildcard={has_wildcard}, content: {body[:200]}",
                                references=["https://owasp.org/www-community/attacks/Silverlight_Cross-Domain_Policy"]
                            ))
                            break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No cross-domain policies on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
