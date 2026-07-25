"""
Plugin 1040: Redis Unauthenticated Access
============================================
Detects Redis servers accessible without authentication.
Real CVEs: CVE-2023-28879, CVE-2022-0543
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class RedisUnauth(NaslPlugin):
    PLUGIN_ID = 1040
    NAME = 'Redis Unauthenticated Access'
    FAMILY = 'Databases'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'The Redis server is accessible without authentication. An attacker '
        'can read, modify, or delete all data in the Redis instance, and '
        'potentially achieve remote code execution via cron persistence.'
    )
    SOLUTION = (
        'Set a strong password using the "requirepass" Redis config directive. '
        'Bind Redis to localhost only. Use network ACLs to restrict access. '
        'Enable TLS for data in transit. Use Redis 6+ ACL features.'
    )
    CVE = ['CVE-2023-28879', 'CVE-2022-0543']
    PORTS = [6379]

    async def check_target(self, target: str, port: int | None = 6379) -> list[PluginResult]:
        port = port or 6379

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            writer.write(b'*1\r\n$4\r\nINFO\r\n')
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 16384:
                    break

            writer.close()
            await writer.wait_closed()

            if not response:
                return [PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='No response from Redis — likely not accessible or service mismatch'
                )]

            text = response.decode('utf-8', errors='ignore')

            if text.startswith('+') or 'redis_version' in text or '# Server' in text:
                role = 'unknown'
                version = 'unknown'
                for line in text.split('\r\n'):
                    if line.startswith('redis_version:'):
                        version = line.split(':', 1)[1]
                    if line.startswith('role:'):
                        role = line.split(':', 1)[1].strip()

                return [PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='critical',
                    description=f'Redis accessible without authentication (v{version}, role: {role})',
                    solution=self.SOLUTION,
                    evidence=f'Redis INFO returned — version: {version}, role: {role}, {len(response)} bytes received',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-28879',
                        'https://www.tenable.com/plugins/nessus/115440',
                    ]
                )]

            if text.startswith('-NOAUTH') or text.startswith('-ERR'):
                return [PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='Redis requires authentication'
                )]

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return [PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Port {port} not reachable'
            )]

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            description='Redis server not detected or requires authentication'
        )]
