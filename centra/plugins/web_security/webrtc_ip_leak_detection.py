import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class WebRTCIPLeakDetection(NaslPlugin):
    PLUGIN_ID = 1276
    NAME = "WebRTC IP Address Leak Detection"
    FAMILY = "Web Security Posture"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Detects if the target application uses WebRTC without proper ICE server configuration or if the application leaks internal IP addresses via WebRTC STUN requests."
    SOLUTION = "Configure WebRTC with a TURN server to mask IP addresses. Use mDNS candidates in modern browsers. Disable WebRTC if not required. Set appropriate Content Security Policy directives."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        webrtc_patterns = [
            "RTCPeerConnection", "createDataChannel", "getUserMedia",
            "webkitRTCPeerConnection", "mozRTCPeerConnection",
            "stun:", "turn:", "iceServers", "peerconnection",
        ]
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = "https" if port_to_check in (443, 8443) else "http"
                ctx = None
                if scheme == "https":
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {host_header}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                response = b""
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                    if not chunk:
                        break
                    response += chunk
                decoded = response.decode("utf-8", errors="replace")
                body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                matches = [p for p in webrtc_patterns if p in body.lower()]
                if matches:
                    severity = "medium" if len(matches) > 2 else "info"
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity=severity,
                        description="WebRTC API usage detected on the page. Internal IP addresses may be leaked through STUN requests.",
                        solution=self.SOLUTION,
                        evidence=f"WebRTC detected via patterns: {', '.join(matches)}",
                        references=self.CVE
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if 'writer' in locals() and writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
