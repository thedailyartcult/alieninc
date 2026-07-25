import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class SpringBootActuatorExposure(NaslPlugin):
    PLUGIN_ID = 1262
    NAME = "Spring Boot Actuator Endpoint Exposure"
    FAMILY = "Web Frameworks"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Spring Boot Actuator endpoints are exposed without proper authentication, allowing attackers to access sensitive application internals including health info, environment variables, heap dumps, and configuration."
    SOLUTION = "Configure Spring Boot Actuator endpoints with proper authentication. Set management.endpoints.web.exposure.include to minimal required endpoints and secure them with Spring Security. Use management.endpoints.web.exposure.exclude=* if not needed."
    CVE = ["CVE-2022-22947"]
    PORTS = [8080, 8443, 80, 443, 9000]

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
                    "/actuator", "/actuator/health", "/actuator/info",
                    "/actuator/env", "/actuator/beans", "/actuator/mappings",
                    "/actuator/configprops", "/actuator/logfile", "/actuator/heapdump",
                    "/actuator/threaddump", "/actuator/metrics", "/actuator/httptrace",
                    "/actuator/loggers", "/actuator/auditevents", "/actuator/scheduledtasks",
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
                    headers_part = decoded.split("\r\n\r\n", 1)[0] if "\r\n\r\n" in decoded else decoded
                    status_line = headers_part.split("\r\n")[0] if headers_part else ""
                    status_code = 0
                    if len(status_line.split(" ")) >= 2:
                        try:
                            status_code = int(status_line.split(" ")[1])
                        except ValueError:
                            pass
                    body = decoded.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in decoded else ""
                    if status_code == 200:
                        if endpoint == "/actuator/health":
                            if "status" in body and any(x in body for x in ["UP", "DOWN", "OUT_OF_SERVICE"]):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=5.3,
                                    severity="medium",
                                    description="Spring Boot Actuator health endpoint exposed without authentication.",
                                    solution=self.SOLUTION,
                                    evidence=f"Actuator endpoint exposed: {endpoint}",
                                    references=self.CVE
                                ))
                        elif endpoint == "/actuator/env":
                            if any(x in body for x in ["java.version", "PATH", "spring.", "server."]):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity=self.severity_from_cvss(self.CVSS_SCORE),
                                    description=self.DESCRIPTION,
                                    solution=self.SOLUTION,
                                    evidence=f"Sensitive environment properties exposed via {endpoint}",
                                    references=self.CVE
                                ))
                        elif endpoint in ("/actuator/heapdump", "/actuator/logfile"):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity=self.severity_from_cvss(self.CVSS_SCORE),
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"Critical actuator endpoint exposed: {endpoint}",
                                references=self.CVE
                            ))
                        else:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=5.3,
                                severity="medium",
                                description=self.DESCRIPTION,
                                solution=self.SOLUTION,
                                evidence=f"Actuator endpoint exposed: {endpoint}",
                                references=self.CVE
                            ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                continue
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
