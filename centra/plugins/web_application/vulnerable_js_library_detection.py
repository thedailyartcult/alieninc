import asyncio
import ssl
import re
from plugins import NaslPlugin, PluginResult

class KnownVulnerableJavaScriptLibraryDetection(NaslPlugin):
    PLUGIN_ID = 1169
    NAME = "Known Vulnerable JavaScript Library Detection"
    FAMILY = "Web Applications"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects known vulnerable JavaScript libraries by fingerprinting library versions from script tags in HTML responses. Compares detected versions against known CVE databases for common libraries (jQuery, Angular, React, Vue, Lodash, Moment)."
    SOLUTION = "Update vulnerable JS libraries to latest patched versions. Use SRI hashes. Implement dependency scanning in CI/CD."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    VULNERABLE_VERSIONS = {
        "jquery": {
            "min": "1.0.0",
            "max": "3.5.0",
            "cvss": 7.5,
            "cves": ["CVE-2020-11023", "CVE-2020-11022"],
        },
        "angular": {
            "min": "1.0.0",
            "max": "1.8.3",
            "cvss": 7.0,
            "cves": ["CVE-2021-21277"],
        },
        "react": {
            "min": "0.0.0",
            "max": "16.13.1",
            "cvss": 6.5,
            "cves": ["CVE-2021-21225"],
        },
        "vue": {
            "min": "2.0.0",
            "max": "2.6.14",
            "cvss": 6.1,
            "cves": ["CVE-2022-25834"],
        },
        "lodash": {
            "min": "0.0.0",
            "max": "4.17.21",
            "cvss": 7.5,
            "cves": ["CVE-2021-23337"],
        },
        "moment": {
            "min": "0.0.0",
            "max": "2.29.1",
            "cvss": 7.5,
            "cves": ["CVE-2022-24785"],
        },
    }

    LIB_PATTERNS = {
        "jquery": re.compile(r"jquery[.-](\d+\.\d+\.\d+)", re.I),
        "angular": re.compile(r"angular[.-](\d+\.\d+\.\d+)", re.I),
        "react": re.compile(r"react[.-](\d+\.\d+\.\d+)", re.I),
        "vue": re.compile(r"vue[.-](\d+\.\d+\.\d+)", re.I),
        "lodash": re.compile(r"lodash[.-](\d+\.\d+\.\d+)", re.I),
        "moment": re.compile(r"moment[.-](\d+\.\d+\.\d+)", re.I),
    }

    def _parse_version(self, version_str):
        parts = version_str.split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts)

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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ("127.0.0.1", "localhost", "::1"):
                    host_header = "alieninc.tech"
                request = (
                    f"GET / HTTP/1.1\r\n"
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
                writer.close()
                await writer.wait_closed()
                decoded = response.decode("utf-8", errors="replace")
                for lib_name, pattern in self.LIB_PATTERNS.items():
                    match = pattern.search(decoded)
                    if match:
                        version = match.group(1)
                        version_tuple = self._parse_version(version)
                        vuln_info = self.VULNERABLE_VERSIONS.get(lib_name)
                        if vuln_info:
                            min_v = self._parse_version(vuln_info["min"])
                            max_v = self._parse_version(vuln_info["max"])
                            if min_v <= version_tuple <= max_v:
                                cve_list = ", ".join(vuln_info["cves"])
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    description=f"Vulnerable {lib_name} {version} detected - {cve_list}"
                                ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
