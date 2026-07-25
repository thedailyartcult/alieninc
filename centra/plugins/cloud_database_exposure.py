import asyncio
from plugins import NaslPlugin, PluginResult


class CloudDatabaseExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1329
    NAME = "Cloud Database Public Exposure Detection"
    DESCRIPTION = "Detects publicly accessible cloud database endpoints including AWS RDS, Azure SQL, GCP Cloud SQL, MongoDB Atlas, and other managed database services that should not be internet-facing."
    SOLUTION = "Restrict database access to specific IP ranges and VPC boundaries. Use private IP endpoints. Enable firewall rules and VPC service controls."
    CVSS_SCORE = 8.5
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443, 3306, 5432, 27017, 6379, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        db_signatures = {
            "AWS RDS": [".rds.amazonaws.com", "rds:"],
            "Azure SQL": [".database.windows.net", ".database.azure.com"],
            "GCP Cloud SQL": [".sql.goog", "cloudsql"],
            "MongoDB Atlas": [".mongodb.net", "mongodb+srv://"],
            "Redis Cloud": [".redis.cache.windows.net", ".redis.gov"],
            "ElastiCache": [".cache.amazonaws.com", ".cache.rds"],
        }
        for p in ([port] if port else self.PORTS):
            if p in [3306, 5432, 27017, 6379]:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, p), timeout=5
                    )
                    banner = await asyncio.wait_for(reader.read(256), timeout=3)
                    writer.close()
                    await writer.wait_closed()
                    banner_str = banner.decode("utf-8", errors="replace")
                    for db_name, sigs in db_signatures.items():
                        for sig in sigs:
                            if sig.lower() in banner_str.lower():
                                results.append(PluginResult(
                                    vulnerable=True, target=target, port=p,
                                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                    description=f"{self.DESCRIPTION} {db_name} exposed on port {p}",
                                    solution=self.SOLUTION,
                                    evidence=f"Database banner: {banner_str[:200]}",
                                    references=["https://owasp.org/www-project-web-security-testing-guide/"]
                                ))
                                break
                        else:
                            continue
                        break
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=p,
                            cvss_score=0, severity="Info",
                            description=f"Port {p} open but not a known cloud database",
                            solution="", evidence="", references=[]
                        ))
                except Exception:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"Could not connect to port {p}",
                        solution="", evidence="", references=[]
                    ))
            else:
                for path in ["/", "/config", "/env", "/.env"]:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, p), timeout=5
                        )
                        request = (
                            f"GET {path} HTTP/1.1\r\n"
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
                        findings = []
                        for db_name, sigs in db_signatures.items():
                            for sig in sigs:
                                if sig.lower() in body.lower():
                                    findings.append(f"{db_name} ({sig})")
                                    break
                        if findings:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} Cloud DB references found on port {p}",
                                solution=self.SOLUTION,
                                evidence="; ".join(findings),
                                references=[]
                            ))
                            break
                    except Exception:
                        continue
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=p,
                        cvss_score=0, severity="Info",
                        description=f"No cloud database exposure on port {p}",
                        solution="", evidence="", references=[]
                    ))
        return results
