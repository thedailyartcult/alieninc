import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class JBossDeserialization12149(NaslPlugin):
    PLUGIN_ID = 1259
    NAME = "JBoss JMX Deserialization RCE (CVE-2017-12149)"
    FAMILY = "Web Servers"
    CVSS_SCORE = 9.8
    DESCRIPTION = "JBoss Application Server 5.x and 6.x is vulnerable to a Java deserialization remote code execution via the /invoker/JMXInvokerServlet endpoint, allowing unauthenticated attackers to execute arbitrary code."
    SOLUTION = "Upgrade to a supported JBoss/WildFly version. Disable or restrict access to JMXInvokerServlet."
    CVE = ["CVE-2017-12149"]
    PORTS = [8080, 8443, 80, 443, 9990]

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
                endpoints = [
                    "/invoker/JMXInvokerServlet",
                    "/jmx-console/",
                    "/web-console/",
                ]
                for endpoint in endpoints:
                    request = (
                        f"GET {endpoint} HTTP/1.1\r\n"
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
                    if any(x in body.lower() for x in ["jmxinvoker", "jmx console", "jboss", "html>"]):
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            cvss_score=self.CVSS_SCORE,
                            severity=self.severity_from_cvss(self.CVSS_SCORE),
                            description=self.DESCRIPTION,
                            solution=self.SOLUTION,
                            evidence=f"JBoss deserialization endpoint exposed: {endpoint}",
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
