import asyncio
from plugins import NaslPlugin, PluginResult


class BackupFileExposurePlugin(NaslPlugin):
    PLUGIN_ID = 1365
    NAME = "Backup File Exposure Detection"
    DESCRIPTION = "Detects common backup file extensions and temporary files exposed on web servers that can leak source code, configuration, database credentials, and other sensitive information."
    SOLUTION = "Remove backup files from production web servers. Configure web server to deny access to backup/temp file patterns (*.bak, *.old, *.swp, *.save, ~$*)."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        backup_paths = [
            "/index.php.bak", "/index.php.old", "/index.php.save",
            "/wp-config.php.bak", "/config.php.bak", "/config.php.old",
            "/config.bak", "/config.old", "/config.php~",
            "/.env.bak", "/.env.old", "/.env.save",
            "/db.sql.bak", "/dump.sql", "/backup.sql",
            "/.vimrc", "/.swp", "/index.php.swp",
            "/composer.json.bak", "/package.json.bak",
        ]
        for p in ([port] if port else self.PORTS):
            for path in backup_paths:
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
                    if "HTTP/1.1 200" in body:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Backup file exposed at {path} on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Backup file accessible: {path} ({len(body)} bytes)",
                            references=["https://owasp.org/www-project-web-security-testing-guide/"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No backup files on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
