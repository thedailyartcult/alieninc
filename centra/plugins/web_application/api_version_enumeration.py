import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class APIVersionEnumeration(NaslPlugin):
    PLUGIN_ID = 1293
    NAME = "API Version Enumeration"
    FAMILY = "Web Application Security"
    CVSS_SCORE = 5.0
    DESCRIPTION = "Enumerates API versions to detect outdated or deprecated API versions that may not receive security updates."
    SOLUTION = "Properly deprecate and remove old API versions. Use API versioning with sunset headers. Block access to deprecated versions. Maintain security patches for supported versions."
    CVE = ["CVE-2024-24384"]
    PORTS = [80, 443, 8080, 8443, 3000, 5000]

    VERSIONS = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "latest", "stable", "beta", "alpha", "dev"]
    BASE_PATHS = ["/api", "/api/", "/api/rest", "/api/graphql", "/v1", "/v2", "/v3"]

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
                found_versions = []
                for base in self.BASE_PATHS:
                    for version in self.VERSIONS:
                        if base in ("/v1", "/v2", "/v3"):
                            path = base
                        else:
                            path = f"{base}/{version}"
                        request = (
                            f"GET {path} HTTP/1.1\r\n"
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
                                cl_match = re.search(rb"Content-Length:\s*(\d+)", headers, re.I)
                                if cl_match:
                                    content_length = int(cl_match.group(1))
                                    if len(body) >= content_length:
                                        break
                                else:
                                    break
                        decoded = response.decode("utf-8", errors="replace")
                        status_line = decoded.split("\r\n")[0] if decoded else ""
                        header_section = decoded.split("\r\n\r\n")[0] if "\r\n\r\n" in decoded else decoded
                        ct = ""
                        ct_match = re.search(r"Content-Type:\s*(\S+)", header_section, re.I)
                        if ct_match:
                            ct = ct_match.group(1)
                        if any(s in status_line for s in ["200", "201", "301", "302", "403", "401"]):
                            if "json" in ct or "xml" in ct or "200" in status_line or "201" in status_line:
                                label = version if base in ("/v1", "/v2", "/v3") else f"{base}/{version}"
                                found_versions.append(label)
                                if len(found_versions) >= 3:
                                    break
                    if len(found_versions) >= 3:
                        break
                if found_versions:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity="medium",
                        description=self.DESCRIPTION,
                        solution=self.SOLUTION,
                        evidence=f"API versions detected: {', '.join(found_versions)}",
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
