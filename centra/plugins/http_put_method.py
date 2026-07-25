import asyncio
from plugins import NaslPlugin, PluginResult


class HttpPutMethodPlugin(NaslPlugin):
    PLUGIN_ID = 1378
    NAME = "HTTP PUT Method Enabled Detection"
    DESCRIPTION = "Detects if the HTTP PUT method is enabled on web servers. PUT method allows file upload to the server which can be abused to deploy malicious files if not properly restricted."
    SOLUTION = "Disable the PUT method on production web servers. Restrict PUT to specific authenticated users and directories with WebDAV."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                body = "CentraTest"
                request = (
                    f"PUT /centra_test_{p}.txt HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{body}"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                resp_body = resp.decode("utf-8", errors="replace")
                if "HTTP/1.1 200" in resp_body or "HTTP/1.1 201" in resp_body or "HTTP/1.1 204" in resp_body:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=f"{self.DESCRIPTION} PUT method enabled on port {p}",
                        solution=self.SOLUTION,
                        evidence="PUT request succeeded - file upload possible",
                        references=["https://owasp.org/www-community/attacks/HTTP_PUT"]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"PUT method disabled on port {p}",
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
