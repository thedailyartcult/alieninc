import asyncio
from plugins import NaslPlugin, PluginResult


class DirectoryListingCheckPlugin(NaslPlugin):
    PLUGIN_ID = 1311
    NAME = "Directory Listing Detection"
    DESCRIPTION = "Detects enabled directory listing on web servers by probing common paths and checking for listing indicators such as 'Index of /', 'Directory listing for', and file/folder listings."
    SOLUTION = "Disable directory listing on the web server. For Apache: Options -Indexes. For Nginx: autoindex off. For IIS: disable Directory Browsing."
    CVSS_SCORE = 5.3
    SEVERITY = "Medium"
    FAMILY = "Web Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            listing_found = False
            evidence = ""
            for path in ["/", "/images/", "/css/", "/js/", "/uploads/", "/backup/", "/logs/", "/assets/"]:
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
                    indicators = ["Index of /", "Directory listing for", "[DIR]", "Parent Directory</a>", "Directory: </title>"]
                    for ind in indicators:
                        if ind in body:
                            listing_found = True
                            evidence += f"Path '{path}': {ind} | "
                            break
                except Exception:
                    continue
                if listing_found:
                    break
            if listing_found:
                results.append(PluginResult(
                    vulnerable=True, target=target, port=p,
                    cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                    description=f"{self.DESCRIPTION} Directory listing enabled on port {p}",
                    solution=self.SOLUTION,
                    evidence=evidence.strip(" | "),
                    references=["https://owasp.org/www-community/attacks/Forced_browsing"]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No directory listing detected on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
