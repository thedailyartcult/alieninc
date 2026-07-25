"""
Plugin 1149: security.txt File Detection
==========================================
Detects the presence of a security.txt file per RFC 9116.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class SecurityTxtDetection(NaslPlugin):
    PLUGIN_ID = 1149
    NAME = 'security.txt File Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 1.0
    DESCRIPTION = (
        'Detects the presence of a security.txt file at /.well-known/security.txt '
        'or /security.txt. The security.txt file is a standard (RFC 9116) that '
        'defines a standardized location for security researchers to report '
        'vulnerabilities. Its absence is informational but does not indicate a '
        'vulnerability.'
    )
    SOLUTION = (
        'Create a security.txt file at /.well-known/security.txt with contact '
        'information and disclosure policy.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SECURITY_TXT_PATHS = [
        '/.well-known/security.txt',
        '/security.txt',
    ]

    REQUIRED_FIELDS = [
        'contact',
        'expires',
    ]

    RECOMMENDED_FIELDS = [
        'encryption',
        'acknowledgments',
        'preferred-languages',
        'canonical',
        'policy',
        'hiring',
    ]

    EXPECTED_FIELDS_PATTERN = r'^[a-z][a-z-]+:'

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            for path in self.SECURITY_TXT_PATHS:
                try:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE

                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port_to_check, ssl=ctx),
                        timeout=5
                    )

                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'

                    req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                    writer.write(req.encode())
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

                    header_section, _, body = response.partition(b'\r\n\r\n')
                    status_line = header_section.decode('utf-8', errors='ignore').split('\r\n')[0] if header_section else ''
                    status_code = 0
                    if status_line:
                        try:
                            status_code = int(status_line.split(' ')[1])
                        except (IndexError, ValueError):
                            pass

                    if status_code != 200 or not body:
                        continue

                    body_text = body.decode('utf-8', errors='ignore')

                    if not self._is_security_txt(body_text):
                        continue

                    present_fields = self._parse_fields(body_text)
                    missing_required = [f for f in self.REQUIRED_FIELDS if f not in present_fields]
                    present_recommended = [f for f in self.RECOMMENDED_FIELDS if f in present_fields]

                    detail_parts = [f'Found at {path}']
                    if missing_required:
                        detail_parts.append(f'Missing required field(s): {", ".join(missing_required)}')
                    if present_recommended:
                        detail_parts.append(f'Present recommended: {", ".join(present_recommended)}')

                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        cvss_score=0.0, severity='info',
                        description=f'security.txt found at {path}',
                        solution=self.SOLUTION,
                        evidence=' | '.join(detail_parts),
                        references=[
                            'https://datatracker.ietf.org/doc/html/rfc9116',
                            'https://securitytxt.org/',
                        ]
                    ))

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                cvss_score=0.0, severity='info',
                description='No security.txt file found. Consider creating one per RFC 9116.',
                solution=self.SOLUTION,
                references=[
                    'https://datatracker.ietf.org/doc/html/rfc9116',
                    'https://securitytxt.org/',
                ]
            ))

        return results

    def _is_security_txt(self, body: str) -> bool:
        if re.search(r'^contact:', body, re.MULTILINE | re.IGNORECASE):
            return True
        if re.search(r'^expires:', body, re.MULTILINE | re.IGNORECASE):
            return True
        if re.search(r'^encryption:', body, re.MULTILINE | re.IGNORECASE):
            return True
        if re.search(r'^acknowledgments:', body, re.MULTILINE | re.IGNORECASE):
            return True
        if re.search(r'canonical', body, re.IGNORECASE) and re.search(r'contact', body, re.IGNORECASE):
            return True
        return False

    def _parse_fields(self, body: str) -> list[str]:
        fields = []
        for line in body.split('\n'):
            line = line.strip()
            if re.match(self.EXPECTED_FIELDS_PATTERN, line):
                field_name = line.split(':', 1)[0].strip().lower()
                if field_name not in fields:
                    fields.append(field_name)
        return fields
