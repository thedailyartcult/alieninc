import asyncio
from plugins import NaslPlugin, PluginResult


class MicroserviceFrameworkDetectionPlugin(NaslPlugin):
    PLUGIN_ID = 1325
    NAME = "Microservice Framework Detection"
    DESCRIPTION = "Detects microservice frameworks and runtime environments by fingerprinting response headers, error pages, and default endpoints. Identifies Spring Boot, Quarkus, Micronaut, FastAPI, Express.js, Flask, and others."
    SOLUTION = "No remediation needed; informational check. Remove framework-specific headers and error pages in production."
    CVSS_SCORE = 0
    SEVERITY = "Info"
    FAMILY = "Information Gathering"
    CVE = []
    PORTS = [80, 443, 3000, 8080, 8443, 5000]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        framework_sigs = {
            "Spring Boot": ["spring", "spring-boot", "actuator", "X-Application-Context"],
            "Quarkus": ["quarkus", "x-quarkus", "QKS"],
            "Micronaut": ["micronaut", "x-micronaut"],
            "FastAPI": ["fastapi", "starlette", "uvicorn"],
            "Flask": ["flask", "werkzeug", "python/"],
            "Express.js": ["express", "x-powered-by: express", "etag: w/"],
            "Django": ["django", "wsgi", "python/", "csrftoken"],
            "Ruby on Rails": ["rails", "x-request-id", "x-runtime"],
            "ASP.NET Core": ["asp.net", "x-aspnet", ".net"],
            "Go Gin": ["gin", "golang"],
            "Ktor": ["ktor", "kotlin"],
            "NestJS": ["nestjs", "nest"],
        }
        for p in ([port] if port else self.PORTS):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p), timeout=5
                )
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}:{p}\r\n"
                    f"User-Agent: CentraScanner/1.0\r\n"
                    f"Accept: */*\r\n"
                    f"Connection: close\r\n\r\n"
                )
                writer.write(request.encode())
                await writer.drain()
                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                writer.close()
                await writer.wait_closed()
                body = resp.decode("utf-8", errors="replace")
                detected = []
                for fw_name, sigs in framework_sigs.items():
                    for sig in sigs:
                        if sig.lower() in body.lower():
                            detected.append(fw_name)
                            break
                if detected:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Framework(s) detected on port {p}: {', '.join(set(detected))}",
                        solution="",
                        evidence=f"Framework signatures: {', '.join(set(detected))}",
                        references=[]
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No known framework detected on port {p}",
                        solution="", evidence="", references=[]
                    ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not connect to port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
