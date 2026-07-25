import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class OpensslCipherPlugin(NaslPlugin):
    PLUGIN_ID = 1344
    NAME = "OpenSSL Incorrect Cipher Caching (CVE-2023-5363)"
    DESCRIPTION = "OpenSSL 3.0.0-3.0.12, 3.1.0-3.1.4 contain an incorrect cipher key caching vulnerability that may allow an attacker to recover the encryption key under certain conditions."
    SOLUTION = "Upgrade OpenSSL to 3.0.13, 3.1.5, or 3.2.0+. Apply vendor patches for all affected application stacks."
    CVSS_SCORE = 5.9
    SEVERITY = "Medium"
    FAMILY = "Network Devices"
    CVE = ["CVE-2023-5363"]
    PORTS = [443, 8443, 465, 993, 995]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for p in ([port] if port else self.PORTS):
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, p, ssl=ctx), timeout=5
                )
                writer.write(b"GET / HTTP/1.0\r\nHost: {}\r\n\r\n".format(target.encode()))
                await writer.drain()
                await asyncio.wait_for(reader.read(4096), timeout=5)
                sock = writer.transport.get_extra_info('socket')
                sock = writer.transport.get_extra_info('ssl_object')
                cipher_name = "TLS"
                if sock and hasattr(sock, 'cipher'):
                    cipher_name = sock.cipher()[0]
                writer.close()
                await writer.wait_closed()
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"TLS service detected on port {p} (cipher: {cipher_name})",
                    solution="",
                    evidence=f"TLS service on port {p} with cipher {cipher_name}",
                    references=[f"https://nvd.nist.gov/vuln/detail/{self.CVE[0]}"]
                ))
            except Exception:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=p,
                    cvss_score=0, severity="Info",
                    description=f"Could not establish TLS on port {p}",
                    solution="", evidence="", references=[]
                ))
        return results
