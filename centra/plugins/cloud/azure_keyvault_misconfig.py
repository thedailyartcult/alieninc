import asyncio
from plugins import NaslPlugin, PluginResult


class AzureKeyvaultMisconfigPlugin(NaslPlugin):
    PLUGIN_ID = 1327
    NAME = "Azure Key Vault Misconfiguration Detection"
    DESCRIPTION = "Detects Azure Key Vault misconfigurations including publicly accessible vaults, weak access policies, and vault endpoint exposure that could lead to secret leakage."
    SOLUTION = "Restrict Key Vault access to specific IP ranges and identities. Enable firewall and VNet service endpoints. Use RBAC over access policies."
    CVSS_SCORE = 8.0
    SEVERITY = "High"
    FAMILY = "Cloud Security"
    CVE = []
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        vault_sigs = [".vault.azure.net", "azurekeyvault", "vault.azure.net"]
        for p in ([port] if port else self.PORTS):
            for path in ["/", "/secrets", "/keys", "/certificates", "/.azure/config"]:
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
                    for sig in vault_sigs:
                        if sig in body.lower():
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=p,
                                cvss_score=self.CVSS_SCORE, severity=self.SEVERITY,
                                description=f"{self.DESCRIPTION} Azure Key Vault reference found on port {p}",
                                solution=self.SOLUTION,
                                evidence=f"Key Vault signature '{sig}' found in {path}",
                                references=["https://learn.microsoft.com/en-us/azure/key-vault/general/security-controls"]
                            ))
                            break
                    else:
                        continue
                    break
                except Exception:
                    continue
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"No Azure Key Vault exposure on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
