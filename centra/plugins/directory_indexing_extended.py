import asyncio
from plugins import NaslPlugin, PluginResult


class DirectoryIndexingExtendedPlugin(NaslPlugin):
    PLUGIN_ID = 1385
    NAME = "Extended Directory Indexing Detection"
    DESCRIPTION = "Extended directory indexing detection across multiple web server types (Apache, Nginx, IIS, Tomcat). Detects exposed directory listings that leak file structure, configuration files, and sensitive data."
    SOLUTION = "Disable directory indexing. For Apache: Options -Indexes. For Nginx: autoindex off. For IIS: Disable Directory Browsing."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        index_paths = [
            "/", "/images/", "/img/", "/css/", "/js/",
            "/assets/", "/static/", "/uploads/", "/files/",
            "/backup/", "/logs/", "/downloads/", "/tmp/",
            "/WEB-INF/", "/META-INF/", "/includes/",
        ]
        index_indicators = [
            "Index of /", "Directory listing for", "[DIR]",
            "Parent Directory</a>", "Directory: </title>",
            "Directory Listing: ", "Directory Listing For",
            "modified</a>", "filename</a>",
            "<title>Index of", "Last modified",
        ]
        for p in ([port] if port else self.PORTS):
            for path in index_paths:
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
                    for indicator in index_indicators:
                        if indicator in body:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} Directory indexing at {path} on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Index indicator '{indicator}' found at {path}",
                                references=["https://owasp.org/www-community/attacks/Forced_browsing"]
                            ))
                            break
                    if results:
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No extended directory indexing on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
