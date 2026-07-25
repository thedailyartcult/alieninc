import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class SensitiveHTTPHeaderInformationDisclosure(NaslPlugin):
    PLUGIN_ID = 1170
    NAME = "Sensitive HTTP Header Information Disclosure"
    FAMILY = "Web Applications"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Detects sensitive information disclosed in HTTP response headers including server versions, framework versions, X-Powered-By values, and internal IP addresses. This information helps attackers target specific vulnerabilities."
    SOLUTION = "Remove or obscure version information from server headers. Use server_tokens off in Nginx. Customize error pages."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATTERNS = [
        re.compile(r"Server:\s+\S+/(\d+\.\d+)", re.I),
        re.compile(r"X-Powered-By:\s+\S+", re.I),
        re.compile(r"X-AspNet-Version:\s+\S+", re.I),
        re.compile(r"X-AspNetMvc-Version:\s+\S+", re.I),
        re.compile(r"X-Generator:\s+\S+", re.I),
        re.compile(r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"),
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
                writer.close()
                await writer.wait_closed()
                decoded = response.decode("utf-8", errors="replace")
                header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                findings = []
                for pattern in self.SENSITIVE_PATTERNS:
                    match = pattern.search(header_section)
                    if match:
                        findings.append(match.group(0).strip())
                if findings:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        description=f"Sensitive information disclosed in headers: {'; '.join(findings)}"
                    ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
