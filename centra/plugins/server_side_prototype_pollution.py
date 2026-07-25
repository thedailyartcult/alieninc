import asyncio
from plugins import NaslPlugin, PluginResult


class ServerSidePrototypePollutionPlugin(NaslPlugin):
    PLUGIN_ID = 1351
    NAME = "Server-Side Prototype Pollution Detection"
    DESCRIPTION = "Tests for server-side prototype pollution vulnerabilities by injecting __proto__ and constructor.prototype payloads into JSON bodies and checking for reflected properties."
    SOLUTION = "Use Object.create(null) for lookup objects. Validate all JSON input. Freeze prototypes with Object.freeze(). Use schema validation libraries."
    CVSS_SCORE = 7.5
    SEVERITY = "High"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 3000, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        pp_payloads = [
            ('{"__proto__":{"polluted":"true"}}', "__proto__ injection"),
            ('{"constructor":{"prototype":{"polluted":"true"}}}', "constructor.prototype injection"),
        ]
        for p in ([port] if port else self.PORTS):
            for path in ["/api", "/api/v1", "/", "/api/user", "/api/update"]:
                found = False
                for payload, desc in pp_payloads:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        request = (
                            f"POST {path} HTTP/1.1\r\n"
                            f"Host: {target}:{p}\r\n"
                            f"Content-Type: application/json\r\n"
                            f"Content-Length: {len(payload)}\r\n"
                            f"User-Agent: CentraScanner/1.0\r\n"
                            f"Connection: close\r\n\r\n"
                            f"{payload}"
                        )
                        writer.write(request.encode())
                        await writer.drain()
                        resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                        writer.close()
                        await writer.wait_closed()
                        body = resp.decode("utf-8", errors="replace")
                        if "true" in body and ("polluted" in body):
                            found = True
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} Server-side prototype pollution on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Prototype pollution via {desc} on {path}",
                                references=["https://portswigger.net/web-security/prototype-pollution"]
                            ))
                            break
                    except Exception:
                        continue
                if found:
                    break
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No server-side PP on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
