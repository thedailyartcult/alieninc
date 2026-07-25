import asyncio
from plugins import NaslPlugin, PluginResult


class WebsocketSecurityCheckPlugin(NaslPlugin):
    PLUGIN_ID = 1323
    NAME = "WebSocket Endpoint Security Check"
    DESCRIPTION = "Checks for WebSocket endpoints that may bypass HTTP authentication and security controls. Unauthenticated WebSocket connections can expose real-time data streams and functionality."
    SOLUTION = "Authenticate WebSocket connections using token-based auth. Apply same access controls as HTTP endpoints. Validate origin headers."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "API Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        ws_paths = ["/ws", "/websocket", "/socket", "/sockjs", "/ws/", "/socket.io/"]
        for p in ([port] if port else self.PORTS):
            ws_found = []
            for path in ws_paths:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {target}:{p}\r\n"
                        f"Upgrade: websocket\r\n"
                        f"Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                        f"Sec-WebSocket-Version: 13\r\n"
                        f"User-Agent: CentraScanner/1.0\r\n"
                        f"Accept: */*\r\n\r\n"
                    )
                    writer.write(request.encode())
                    await writer.drain()
                    resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                    writer.close()
                    await writer.wait_closed()
                    body = resp.decode("utf-8", errors="replace")
                    if "HTTP/1.1 101" in body or "websocket" in body.lower():
                        ws_found.append(path)
                except Exception:
                    continue
            if ws_found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} WebSocket endpoints exposed on port {p}",
                    solution=self.SOLUTION,
                    evidence=f"WebSocket paths: {', '.join(ws_found)}",
                    references=["https://owasp.org/API-Security/editions/2023/en/0xa8-injection/"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No WebSocket endpoints detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
