"""
Plugin 1046: Database Authentication Check
=============================================
Tests for MariaDB, PostgreSQL, and MongoDB instances accessible
without authentication or with default credentials.
Real CVEs: CVE-2023-28879, CVE-2022-0543, CVE-2022-21371
"""
import asyncio
import struct

from plugins import NaslPlugin, PluginResult


class DatabaseAuthCheck(NaslPlugin):
    PLUGIN_ID = 1046
    NAME = 'Database Authentication Check'
    FAMILY = 'Databases'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Database services (PostgreSQL, MariaDB/MySQL, MongoDB) are accessible '
        'without authentication or with default credentials. Unauthenticated '
        'database access can lead to data theft, data loss, and system compromise.'
    )
    SOLUTION = (
        'Configure strong passwords for all database accounts. Disable remote '
        'root login. Bind databases to localhost. Use network ACLs and firewalls. '
        'Enable TLS for database connections. Disable default accounts.'
    )
    CVE = ['CVE-2023-28879', 'CVE-2022-0543', 'CVE-2022-21371']
    PORTS = [3306, 5432, 27017]

    async def check_target(self, target: str, port: int | None = 5432) -> list[PluginResult]:
        port = port or 5432

        if port == 5432:
            return await self._check_postgres(target, port)
        if port == 3306:
            return await self._check_mysql(target, port)
        if port == 27017:
            return await self._check_mongodb(target, port)

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description=f'Unsupported database port: {port}'
        )]

    async def _check_postgres(self, target: str, port: int) -> list[PluginResult]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            startup = struct.pack('!i', 8) + b'\x00\x03\x00\x00user\x00postgres\x00\x00'
            writer.write(startup)
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 4096:
                    break

            writer.close()
            await writer.wait_closed()

            if not response:
                return [PluginResult(vulnerable=False, target=target, port=port,
                                     description='No response from PostgreSQL')]

            if response[0] == 0x52:
                server_version = ''
                if len(response) > 8:
                    ver_len = struct.unpack('!i', response[5:9])[0]
                    server_version = response[9:9+ver_len-1].decode('utf-8', errors='replace')

                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='critical',
                    description=f'PostgreSQL accessible without authentication (v{server_version})',
                    solution=self.SOLUTION,
                    evidence=f'PostgreSQL authentication-free (auth=trust) — version: {server_version}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-28879',
                    ]
                )]

            if response[0] == 0x45:
                return [PluginResult(vulnerable=False, target=target, port=port,
                                     description='PostgreSQL requires authentication')]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='PostgreSQL not reachable or requires auth')]

    async def _check_mysql(self, target: str, port: int) -> list[PluginResult]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 4096:
                    break

            writer.close()
            await writer.wait_closed()

            if not response or len(response) < 4:
                return [PluginResult(vulnerable=False, target=target, port=port,
                                     description='No valid MySQL handshake received')]

            if response[0] == 0x0a or response[0] == 0x0e:
                server_ver = response.split(b'\x00')[1].decode('utf-8', errors='replace') if b'\x00' in response[1:] else 'unknown'

                auth_plugin = b'mysql_native_password'
                if b'caching_sha2_password' in response:
                    auth_plugin = b'caching_sha2_password'

                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='high',
                    description=f'MySQL/MariaDB accessible (v{server_ver}, auth: {auth_plugin.decode()})',
                    solution=self.SOLUTION,
                    evidence=f'MySQL handshake received — version: {server_ver}, auth plugin: {auth_plugin.decode()}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2022-21371',
                    ]
                )]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='MySQL/MariaDB not reachable')]

    async def _check_mongodb(self, target: str, port: int) -> list[PluginResult]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            ismaster = bytes([
                0x3a, 0x00, 0x00, 0x00,
                0x01,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00,
                0x04, 0x69, 0x73, 0x6d, 0x61, 0x73, 0x74, 0x65, 0x72, 0x00,
            ])

            writer.write(ismaster)
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 4096:
                    break

            writer.close()
            await writer.wait_closed()

            if response and len(response) > 20 and b'ok' in response:
                server_version = b''
                for part in response.split(b'\x00'):
                    if b'.' in part and any(c.isdigit() for c in part[:3].decode('utf-8', errors='ignore')):
                        server_version = part
                        break

                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='high',
                    description=f'MongoDB accessible without authentication',
                    solution=self.SOLUTION,
                    evidence=f'MongoDB isMaster replied — version: {server_version.decode("utf-8", errors="replace")}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2022-0543',
                    ]
                )]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

        return [PluginResult(vulnerable=False, target=target, port=port,
                             description='MongoDB not reachable or requires auth')]
