import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class OpenCloudStorageBucketDetection(NaslPlugin):
    PLUGIN_ID = 1168
    NAME = "Open Cloud Storage Bucket Detection"
    FAMILY = "Cloud Infrastructure"
    CVSS_SCORE = 7.5
    DESCRIPTION = "Detects publicly accessible cloud storage buckets by probing common bucket naming patterns based on the target domain. Open buckets can expose sensitive data including customer information, source code, and credentials."
    SOLUTION = "Use private ACLs for all storage buckets. Regularly audit bucket permissions. Implement least-privilege access."
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        domain_parts = target.split(".")
        base = domain_parts[0] if len(domain_parts) > 0 else target
        bucket_names = [
            f"{base}",
            f"{base}-backup",
            f"{base}-data",
            f"{base}-assets",
            f"{base}-storage",
            f"{base}-media",
            f"{base}-public",
            f"{base}-uploads",
            f"{base}-files",
            f"{base}-static",
        ]
        for port_to_check in (self.PORTS if port is None else [port]):
            for bucket in bucket_names:
                try:
                    scheme = "https" if port_to_check in (443, 8443) else "http"
                    ctx = None
                    if scheme == "https":
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    urls_to_probe = [
                        f"{bucket}.s3.amazonaws.com",
                        f"{bucket}.storage.googleapis.com",
                        f"{bucket}.blob.core.windows.net",
                    ]
                    for storage_url in urls_to_probe:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(storage_url, 443, ssl=ctx), timeout=5)
                            host_header = storage_url
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
                            status_line = decoded.split("\r\n")[0]
                            if "200" in status_line or "403" in status_line or "ListBucketResult" in decoded:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    description=f"Open or accessible cloud storage bucket found at {storage_url}"
                                ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description="No issues detected"))
        return results
