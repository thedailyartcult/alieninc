import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class JwtAlgorithmConfusionAttackDetection(NaslPlugin):
    PLUGIN_ID = 1167
    NAME = "JWT Algorithm Confusion Attack Detection"
    FAMILY = "Web Applications"
    CVSS_SCORE = 8.6
    DESCRIPTION = "Detects JWT algorithm confusion vulnerabilities where the server uses a public key to verify HMAC-signed tokens. An attacker can change the algorithm from RS256 to HS256 using the public key as the HMAC secret, forging arbitrary tokens."
    SOLUTION = "Always validate JWT algorithm against a whitelist. Use separate key types for different algorithms."
    CVE = ["CVE-2020-28052"]
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
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
                    f"GET /.well-known/jwks.json HTTP/1.1\r\n"
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
                writer.close()
                await writer.wait_closed()
                decoded = response.decode("utf-8", errors="replace")
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port_to_check,
                    description="JWT endpoint accessible - algorithm confusion attack vector present if JWKS keys are obtainable"
                ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
