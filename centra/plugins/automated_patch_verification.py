"""
Plugin 1060: Automated Patch & Fix Verification (Self-Fixing)
================================================================
Verifies that known-vulnerability patches and fixes have been applied
by re-checking the specific conditions that triggered the finding.
Self-fixing pillar: confirms remediation effectiveness.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult, ScanContext


class AutomatedPatchVerification(NaslPlugin):
    PLUGIN_ID = 1060
    NAME = 'Automated Patch & Fix Verification'
    FAMILY = 'Self-Fixing'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Verifies that security patches and configuration fixes have been '
        'applied by re-checking specific vulnerability conditions. This '
        'closes the self-fixing loop: detect → patch → verify. Reports '
        'which fixes are confirmed, which are still pending, and which '
        'need re-application.'
    )
    SOLUTION = (
        'Apply missing patches per vendor advisory. After patching, '
        're-scan with Centra to verify fix effectiveness. Automate '
        'patch verification as part of the CI/CD pipeline.'
    )

    PATCH_CHECKS = {
        'tls_weakness': {
            'name': 'TLS 1.0/1.1 Disabled',
            'check': 'tls_version',
            'protocols': ['TLSv1', 'TLSv1.1'],
        },
        'missing_security_headers': {
            'name': 'Security Headers Added',
            'check': 'http_headers',
            'headers': ['strict-transport-security', 'content-security-policy',
                         'x-content-type-options'],
        },
        'cors_wildcard': {
            'name': 'CORS Origin Restricted',
            'check': 'cors',
        },
    }

    async def check_target(self, target: str, port: int | None = 443,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        port = port or 443
        applied = 0
        pending = 0
        not_testable = 0
        details = []

        for check_id, check_info in self.PATCH_CHECKS.items():
            try:
                patched = await self._verify_patch(target, port, check_id, check_info)
                if patched is None:
                    not_testable += 1
                elif patched:
                    applied += 1
                    details.append(f'  VERIFIED: {check_info["name"]} — fix confirmed')
                else:
                    pending += 1
                    details.append(f'  PENDING: {check_info["name"]} — fix not applied')
            except Exception:
                not_testable += 1

        if pending > 0:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=4.0,
                severity='medium',
                description=f'Patch verification: {applied} verified, {pending} still pending, {not_testable} n/a',
                solution='Apply pending patches and re-verify.',
                evidence=' | '.join(details),
                references=[
                    'https://www.tenable.com/plugins/nessus/141561',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target,
            cvss_score=0.0, severity='info',
            description=f'Patch verification: {applied}/{applied + not_testable} fixes confirmed',
            evidence=' | '.join(details) if details else 'No patches to verify',
        )]

    async def _verify_patch(self, target: str, port: int,
                             check_id: str, check_info: dict) -> bool | None:
        if check_info['check'] == 'tls_version':
            try:
                for proto in check_info['protocols']:
                    for proto_name, ssl_ver in [
                        ('TLSv1', ssl.TLSVersion.TLSv1),
                        ('TLSv1.1', ssl.TLSVersion.TLSv1_1),
                    ]:
                        if proto_name != proto:
                            continue
                        try:
                            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            ctx.maximum_version = ssl_ver
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port, ssl=ctx), timeout=5
                            )
                            writer.close()
                            await writer.wait_closed()
                            return False
                        except (ssl.SSLError, OSError):
                            pass
                return True
            except Exception:
                return None

        if check_info['check'] == 'http_headers':
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
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

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                present = [h for h in check_info['headers'] if h in header_section]
                return len(present) >= len(check_info['headers']) // 2
            except Exception:
                return None

        if check_info['check'] == 'cors':
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=5
                )
                req = f'GET / HTTP/1.1\r\nHost: {target}\r\nOrigin: https://evil.com\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
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

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore').lower()
                for line in header_section.split('\r\n'):
                    if line.startswith('access-control-allow-origin:'):
                        return line.split(':', 1)[1].strip() != '*'
                return True
            except Exception:
                return None

        return None
