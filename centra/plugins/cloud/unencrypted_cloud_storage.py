import asyncio
from plugins import NaslPlugin, PluginResult


class UnencryptedCloudStoragePlugin(NaslPlugin):
    PLUGIN_ID = 1331
    NAME = "Unencrypted Cloud Storage Detection"
    DESCRIPTION = "Detects cloud storage resources that may lack encryption at rest including S3 buckets with disabled SSE, Azure blobs without encryption, and GCP buckets without CMEK."
    SOLUTION = "Enable encryption at rest for all cloud storage resources. Use AWS S3 SSE-S3 or SSE-KMS, Azure Storage Service Encryption, GCP CMEK."
    CVSS_SCORE = 6.5
    SEVERITY = "Medium"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        storage_patterns = [
            "s3.amazonaws.com", "s3-us", "s3-", ".s3.", ".amazonaws.com",
            "blob.core.windows.net", "storage.cloud.google.com",
            "storage.googleapis.com", "digitaloceanspaces.com",
        ]
        encryption_sigs = ["SSE", "encryption", "sse-s3", "sse-kms", "cmek", "encrypt"]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/.s3cfg", "/s3", "/storage", "/backup"]:
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
                    has_storage = any(sig in body for sig in storage_patterns)
                    has_encryption = any(sig in body.lower() for sig in encryption_sigs)
                    if has_storage and not has_encryption:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=p,
                            cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                            description=f"{self.DESCRIPTION} Unencrypted cloud storage reference on port {p}",
                            solution=self.SOLUTION,
                            evidence=f"Storage reference found without encryption config in {path}",
                            references=["https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html"]
                        ))
                        break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No unencrypted storage on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
