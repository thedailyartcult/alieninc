import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class AlienincCspInlineScriptsPlugin(NaslPlugin):
    PLUGIN_ID = 17677
    NAME = "AlienInc CSP Inline Scripts"
    DESCRIPTION = "Content-Security-Policy allows unsafe-inline scripts which may enable XSS."
    SOLUTION = "Remove unsafe-inline from CSP script-src directive."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p, ssl=ssl.create_default_context()), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                headers_resp = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
                resp = await asyncio.wait_for(reader.read(16384), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                headers_lower = headers_resp.decode("utf-8", errors="replace").lower()
                has_header = "unsafe-inline" in headers_lower
                if has_header:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=p,
                        cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"Found header: unsafe-inline",
                        references=self.CVE if self.CVE else []
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description="Check passed",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description="Could not connect",
                    solution="", evidence="", references=[]
                ))
        return results
