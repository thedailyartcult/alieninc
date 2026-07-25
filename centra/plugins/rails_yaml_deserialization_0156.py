import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class RailsYAMLDeserialization0156(NaslPlugin):
    PLUGIN_ID = 1260
    NAME = "Ruby on Rails YAML Deserialization RCE (CVE-2013-0156)"
    FAMILY = "Web Frameworks"
    CVSS_SCORE = 9.8
    DESCRIPTION = "Ruby on Rails 2.3.x before 2.3.16 and 3.0.x before 3.0.20 is vulnerable to a critical remote code execution via YAML deserialization through the JSON parser."
    SOLUTION = "Upgrade Ruby on Rails to version 2.3.16, 3.0.20, 3.1.12, 3.2.13, or later."
    CVE = ["CVE-2013-0156"]
    PORTS = [80, 443, 3000, 8080, 8443]

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
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                test_paths = [
                    "/users/sign_in",
                    "/admin/login",
                    "/home/index",
                    "/rails/info/properties",
                    "/rails/info/routes",
                ]
                for path in test_paths:
                    request = (
                        f"GET {path} HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"X-HTTP-Method-Override: GET\r\n"
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
                    headers_part = decoded.split("\r\n\r\n", 1)[0] if "\r\n\r\n" in decoded else decoded
                    server_header = ""
                    for line in headers_part.split("\r\n"):
                        if line.lower().startswith("server:"):
                            server_header += line.split(":", 1)[1].strip()
                        elif line.lower().startswith("x-powered-by:"):
                            server_header += line.split(":", 1)[1].strip()
                    if any(x in server_header.lower() for x in ["rails", "phusion", "passenger"]):
                        results.append(PluginResult(
                            vulnerable=False,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity="medium",
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"Potential Rails application detected at {path}. Further testing required for YAML deserialization.",
                            references=self.CVE
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
