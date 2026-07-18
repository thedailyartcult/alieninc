"""
Plugin 1002: Anonymous FTP Access Check
========================================
Detects FTP servers allowing anonymous login.
Real CVEs: CVE-2019-5400, CVE-2017-17382, CVE-2014-2968
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class AnonymousFtp(NaslPlugin):
    PLUGIN_ID = 1002
    NAME = 'Anonymous FTP Access'
    FAMILY = 'FTP'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'The remote FTP server allows anonymous login. This may expose sensitive '
        'files or allow unauthorized access to the file system.'
    )
    SOLUTION = (
        'Disable anonymous FTP access on the server. Use SFTP or FTPS with '
        'authentication instead. If anonymous access is required, restrict it '
        'to a read-only chroot directory with no sensitive data.'
    )
    CVE = ['CVE-2019-5400', 'CVE-2017-17382']
    PORTS = [21]

    async def check_target(self, target: str, port: int | None = 21) -> list[PluginResult]:
        port = port or 21
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            banner = await asyncio.wait_for(reader.readline(), timeout=3)
            banner_str = banner.decode('utf-8', errors='ignore').strip()

            if not banner_str.startswith('220'):
                writer.close()
                return []

            writer.write(b'USER anonymous\r\n')
            await writer.drain()
            resp = await asyncio.wait_for(reader.readline(), timeout=3)
            resp_str = resp.decode('utf-8', errors='ignore').strip()

            if '331' in resp_str:
                writer.write(b'PASS anonymous@test.com\r\n')
                await writer.drain()
                resp = await asyncio.wait_for(reader.readline(), timeout=3)
                resp_str = resp.decode('utf-8', errors='ignore').strip()

            writer.write(b'LIST\r\n')
            await writer.drain()
            list_resp = await asyncio.wait_for(reader.readline(), timeout=3)
            list_str = list_resp.decode('utf-8', errors='ignore').strip()

            writer.write(b'QUIT\r\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()

            if '230' in resp_str or '150' in list_str or '226' in list_str:
                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='medium',
                    description=f'FTP server allows anonymous login. Banner: {banner_str[:100]}',
                    solution=self.SOLUTION,
                    evidence=f'Server: {banner_str[:100]} | USER/PASS responses accepted | LIST: {list_str[:100]}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2019-5400',
                        'https://www.tenable.com/plugins/nessus/1004',
                    ]
                )]

            return [PluginResult(vulnerable=False, target=target, port=port)]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(vulnerable=False, target=target, port=port,
                                 description=f'FTP port {port} not reachable')]
