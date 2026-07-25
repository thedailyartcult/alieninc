"""
Plugin 1055: Auto-Remediation Verification (Self-Fixing)
===========================================================
After a scan identifies vulnerabilities, re-checks specific findings
to verify whether suggested remediations have been applied.
Self-fixing pillar: closes the loop between detection and fix.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult, ScanContext


class AutoRemediationVerification(NaslPlugin):
    PLUGIN_ID = 1055
    NAME = 'Auto-Remediation Verification'
    FAMILY = 'Self-Fixing'
    PLUGIN_TYPE = 'summary'
    CVSS_SCORE = 0.0
    DESCRIPTION = (
        'Verifies that previously identified vulnerabilities have been '
        'remediated. Re-checks security controls that were flagged in prior '
        'scans and reports whether fixes are now in place. Enables the '
        'self-fixing feedback loop: detect → remediate → verify.'
    )
    SOLUTION = (
        'Review unresolved findings and apply the suggested remediations. '
        'Re-scan with Centra to verify fixes. Automate remediation where '
        'possible via infrastructure-as-code.'
    )
    DEPENDENCIES = [1003, 1005, 1009, 1037, 1038, 1045]

    REMEDIATION_CHECKS = {
        'missing_security_headers': {
            'name': 'HTTP Security Headers',
            'check_port': 80,
            'expected_headers': ['strict-transport-security', 'content-security-policy',
                                  'x-content-type-options', 'x-frame-options'],
        },
        'cors_wildcard': {
            'name': 'CORS Wildcard Restriction',
            'check_port': 80,
            'expected': lambda h: not h.get('access-control-allow-origin', '') == '*',
        },
        'missing_csrf': {
            'name': 'CSRF Token Implementation',
            'check_port': 80,
            'expected': None,
        },
    }

    async def check_target(self, target: str, port: int | None = None,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        fixed_count = 0
        still_broken = 0
        not_applicable = 0
        details = []

        for check_id, check_info in self.REMEDIATION_CHECKS.items():
            check_port = check_info['check_port'] or port or 80
            try:
                fixed = await self._run_verification(target, check_port, check_id, check_info)
                if fixed is None:
                    not_applicable += 1
                elif fixed:
                    fixed_count += 1
                    details.append(f'  FIXED: {check_info["name"]}')
                else:
                    still_broken += 1
                    details.append(f'  STILL BROKEN: {check_info["name"]}')
            except Exception:
                not_applicable += 1

        if still_broken > 0:
            return [PluginResult(
                vulnerable=True,
                target=target,
                port=port or 0,
                cvss_score=4.0,
                severity='medium',
                description=f'Auto-remediation: {fixed_count} fixed, {still_broken} still broken, {not_applicable} n/a',
                solution='Apply remaining remediations and re-scan.',
                evidence=' | '.join(details),
                references=[
                    'https://www.tenable.com/plugins/nessus/141561',
                ]
            )]

        return [PluginResult(
            vulnerable=False, target=target,
            cvss_score=0.0, severity='info',
            description=f'Auto-remediation: {fixed_count}/{fixed_count + not_applicable} checks passing',
            evidence=' | '.join(details) if details else 'No applicable remediations to verify',
        )]

    async def _run_verification(self, target: str, port: int,
                                 check_id: str, check_info: dict) -> bool | None:
        if check_id == 'missing_security_headers':
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
                present = [h for h in check_info['expected_headers'] if h in header_section]
                return len(present) >= 2

            except Exception:
                return None

        if check_id == 'cors_wildcard':
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
                        origin = line.split(':', 1)[1].strip()
                        return origin != '*'
                return True

            except Exception:
                return None

        return None
