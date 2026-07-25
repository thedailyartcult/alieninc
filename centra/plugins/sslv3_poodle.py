"""
Plugin 1032: SSLv3 / POODLE Detection
========================================
Checks if the server accepts SSLv3 connections (POODLE attack).
Real CVEs: CVE-2014-3566 (POODLE), CVE-2015-0204 (FREAK)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class Sslv3Poodle(NaslPlugin):
    PLUGIN_ID = 1032
    NAME = 'SSLv3 / POODLE Detection'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 6.8
    DESCRIPTION = (
        'The remote service accepts SSL 3.0 connections. The POODLE attack '
        '(Padding Oracle On Downgraded Legacy Encryption) allows a man-in-the-middle '
        'attacker to decrypt ciphertext using a padding oracle side channel.'
    )
    SOLUTION = (
        'Disable SSLv3 on all services. Use TLS 1.2 or higher exclusively. '
        'See CVE-2014-3566 for details.'
    )
    CVE = ['CVE-2014-3566', 'CVE-2015-0204']
    PORTS = [443, 8443, 993, 995, 465, 2525]

    async def check_target(self, target: str, port: int | None = 443) -> list[PluginResult]:
        port = port or 443
        results = []

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.maximum_version = ssl.TLSVersion.SSLv3

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx),
                timeout=5
            )
            writer.close()
            await writer.wait_closed()

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description='Server accepts SSLv3 connections — vulnerable to POODLE attack',
                solution=self.SOLUTION,
                evidence=f'SSLv3 connection accepted on port {port}',
                references=[
                    'https://nvd.nist.gov/vuln/detail/CVE-2014-3566',
                    'https://www.tenable.com/plugins/nessus/78480',
                ]
            ))

        except ssl.SSLError:
            pass
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description='SSLv3 not accepted — server is not vulnerable to POODLE'
            ))

        return results
