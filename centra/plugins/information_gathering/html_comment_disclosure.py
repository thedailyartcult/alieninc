import asyncio
import re
from plugins import NaslPlugin, PluginResult


class HtmlCommentDisclosurePlugin(NaslPlugin):
    PLUGIN_ID = 1381
    NAME = "HTML Comment Information Disclosure"
    DESCRIPTION = "Detects sensitive information in HTML comments including TODO notes, credentials, internal paths, API keys, and developer debug information that may aid attackers."
    SOLUTION = "Remove HTML comments from production builds. Use build tools to strip comments. Never include sensitive info in comments."
    CVSS_SCORE = 4.0
    SEVERITY = "Medium"
    FAMILY = "Information Gathering"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        sensitive_patterns = [
            "TODO", "FIXME", "XXX", "HACK", "BUG",
            "password", "credentials", "secret", "apikey", "api_key",
            "internal", "private", "hidden", "debug",
            "username", "connection_string", "connstr",
            "// TODO", "<!-- TODO", "bypass", "vulnerable",
        ]
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
                resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                comments = re.findall(r'<!--(.*?)-->', body, re.DOTALL)
                sensitive_comments = []
                for comment in comments:
                    comment_lower = comment.lower()
                    for pattern in sensitive_patterns:
                        if pattern.lower() in comment_lower:
                            sensitive_comments.append(comment.strip()[:120])
                            break
                if sensitive_comments:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} {len(sensitive_comments)} sensitive comment(s) on port {p}",
                        solution=self.SOLUTION,
                        evidence=f"Sensitive comments: {'; '.join(sensitive_comments[:5])}",
                        references=["https://owasp.org/www-project-web-security-testing-guide/"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No sensitive comments on port {p}",
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
