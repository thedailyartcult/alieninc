import asyncio
import re
from plugins import NaslPlugin, PluginResult


class EmailAddressDisclosurePlugin(NaslPlugin):
    PLUGIN_ID = 1380
    NAME = "Email Address Disclosure in Source"
    DESCRIPTION = "Detects email addresses disclosed in web page source code that can be harvested for spam, phishing, or social engineering attacks against the organization."
    SOLUTION = "Remove plain email addresses from HTML source. Use contact forms instead of mailto: links. Obfuscate email addresses using JavaScript or image-based methods."
    CVSS_SCORE = 3.7
    SEVERITY = "Low"
    FAMILY = "Information Gathering"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/contact", "/about", "/team", "/contact-us"]:
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
                    emails = re.findall(email_pattern, body)
                    skip_domains = ["example.com", "domain.com", "yourdomain.com"]
                    real_emails = [e for e in emails if not any(s in e for s in skip_domains)]
                    if real_emails:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} {len(real_emails)} email(s) found on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Emails found: {', '.join(real_emails[:10])}",
                            references=["https://owasp.org/www-project-web-security-testing-guide/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No emails disclosed on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
