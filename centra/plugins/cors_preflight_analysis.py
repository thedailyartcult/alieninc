import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class CORSPreflightRequestAnalysis(NaslPlugin):
    PLUGIN_ID = 1175
    NAME = "CORS Preflight Request Analysis"
    FAMILY = "Web Applications"
    CVSS_SCORE = 5.3
    DESCRIPTION = "Analyzes CORS preflight (OPTIONS) responses for security-relevant configuration including allowed methods, allowed headers, max-age, and credential support. Misconfigured preflight responses can weaken overall CORS security posture."
    SOLUTION = "Restrict allowed methods and headers in preflight responses. Use appropriate max-age values. Do not allow credentials on wildcard origins."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TEST_ORIGINS = [
        "https://evil.com",
        "https://attacker.com",
        "null",
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for origin in self.TEST_ORIGINS:
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
                        f"OPTIONS / HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"Origin: {origin}\r\n"
                        f"Access-Control-Request-Method: GET\r\n"
                        f"Access-Control-Request-Headers: X-Custom-Header\r\n"
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
                    acao = re.search(r"Access-Control-Allow-Origin:\s*(\S+)", header_section, re.I)
                    acam = re.search(r"Access-Control-Allow-Methods:\s*(\S+)", header_section, re.I)
                    acah = re.search(r"Access-Control-Allow-Headers:\s*(\S+)", header_section, re.I)
                    acac = re.search(r"Access-Control-Allow-Credentials:\s*(\S+)", header_section, re.I)
                    if acao or acam or acah:
                        findings = []
                        if acao:
                            findings.append(f"ACAO: {acao.group(1)}")
                        if acam:
                            findings.append(f"ACAM: {acam.group(1)}")
                        if acah:
                            findings.append(f"ACAH: {acah.group(1)}")
                        if acac:
                            findings.append(f"ACAC: {acac.group(1)}")
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            description=f"CORS preflight from {origin}: {'; '.join(findings)}"
                        ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
