"""
Plugin 1081: Follina — MSDT RCE (CVE-2022-30190)
==================================================
Detects MSDT vulnerability via ms-msdt protocol handler abuse.
Real CVE: CVE-2022-30190 (CVSS 7.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class FollinaDetection(NaslPlugin):
    PLUGIN_ID = 1081
    NAME = 'Microsoft Support Diagnostic Tool Follina RCE (CVE-2022-30190)'
    FAMILY = 'Windows'
    CVSS_SCORE = 7.8
    DESCRIPTION = (
        'Microsoft Support Diagnostic Tool (MSDT) in Windows is vulnerable to remote '
        'code execution via the ms-msdt URI scheme. When a user opens a specially '
        'crafted Office document or visits a web page that invokes the MSDT diagnostic '
        'tool, an attacker can execute arbitrary code with the privileges of the '
        'calling application. This vulnerability was exploited in the wild as zero-day.'
    )
    SOLUTION = (
        'Apply Microsoft security update from June 2022. Disable MSDT URL protocol '
        'via registry: HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\ScriptedDiagnostics'
        '\\EnableDiagnostics = 0. Educate users not to open untrusted Office documents.'
    )
    CVE = ['CVE-2022-30190']
    PORTS = [80, 443, 8080]

    MSDT_PATTERNS = [
        b'ms-msdt:',
        b'msdt.exe',
        b'ms-msdt',
    ]

    OFFICE_DOC_PATTERNS = [
        b'.doc',
        b'.docx',
        b'.rtf',
        b'application/msword',
        b'application/vnd.openxmlformats-officedocument',
    ]

    PROBE_PATHS = [
        '/',
        '/uploads',
        '/documents',
        '/files',
        '/download',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
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

                for path in self.PROBE_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
                        f'Accept: */*\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer.write(req.encode())
                    await writer.drain()

                    response = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 8192:
                                break
                    except asyncio.TimeoutError:
                        pass

                    if response:
                        status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                        body_start = response.find(b'\r\n\r\n')
                        body = response[body_start + 4:] if body_start != -1 else b''
                        body_str = body.decode('utf-8', errors='ignore')
                        raw_headers = response[:body_start].decode('utf-8', errors='ignore') if body_start != -1 else ''

                        msdt_found = any(p in response for p in self.MSDT_PATTERNS)
                        office_docs_found = any(p in response for p in self.OFFICE_DOC_PATTERNS)
                        content_disposition = b'Content-Disposition: attachment' in response
                        content_type_doc = b'Content-Type: application/msword' in response

                        if msdt_found:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Web application on port {port_to_check} contains ms-msdt '
                                    f'references — potential Follina attack vector'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'ms-msdt references: {msdt_found}, '
                                    f'Office documents: {office_docs_found}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-30190',
                                    'https://www.tenable.com/plugins/nessus/162104',
                                ]
                            ))
                            break

                        if (office_docs_found or content_disposition) and content_type_doc:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Web application on port {port_to_check} serves Office '
                                    f'documents — may be used as Follina delivery vector'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Office docs: {office_docs_found}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2022-30190',
                                    'https://www.tenable.com/plugins/nessus/162104',
                                ]
                            ))
                            break

                writer.close()
                await writer.wait_closed()

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Follina or MSDT indicators detected on checked ports'
            ))

        return results
