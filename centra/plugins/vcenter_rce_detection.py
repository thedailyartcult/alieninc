"""
Plugin 1085: VMware vCenter Server RCE (CVE-2021-21972)
=========================================================
Detects VMware vCenter Server RCE via Virtual SAN Health Check plugin.
Real CVE: CVE-2021-21972 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class VcenterRceDetection(NaslPlugin):
    PLUGIN_ID = 1085
    NAME = 'VMware vCenter Server RCE Detection (CVE-2021-21972)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'The vCenter Server contains a remote code execution vulnerability in the '
        'Virtual SAN Health Check plugin. An attacker with network access to port '
        '443 can issue a specially crafted POST request to execute arbitrary commands '
        'on the vCenter Server operating system. This vulnerability was actively '
        'exploited following disclosure in February 2021.'
    )
    SOLUTION = (
        'Apply VMware security update vCenter Server 7.0 U1c, 6.7 U3l, or 6.5 U3n. '
        'Restrict network access to vCenter management interface. Disable the Virtual '
        'SAN Health Check plugin if not needed.'
    )
    CVE = ['CVE-2021-21972']
    PORTS = [443, 80, 8080, 8443]

    VCENTER_PATHS = [
        '/ui/vropspluginui/rest/services/uploadova',
        '/vcac/',
        '/vsphere-client/',
        '/ui/',
    ]

    VCENTER_HINTS = [
        b'VMware',
        b'vmware',
        b'vCenter',
        b'vSphere',
        b'vropspluginui',
        b'VMware vCenter',
    ]

    VSAN_HINTS = [
        b'uploadova',
        b'vsan',
        b'health',
        b'Virtual SAN',
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

                for path in self.VCENTER_PATHS:
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
                        is_40x = b'40' in response[:50]
                        vcenter_hits = [h for h in self.VCENTER_HINTS if h.lower() in response.lower()]
                        vsan_hits = [h for h in self.VSAN_HINTS if h.lower() in response.lower()]

                        if vcenter_hits and (is_200 or is_40x):
                            vsan_accessible = vsan_hits and 'uploadova' in path
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'VMware vCenter Server detected on port {port_to_check} — '
                                    f'VSAN Health Check plugin path may be exploitable (CVE-2021-21972)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'vCenter: {vcenter_hits}, '
                                    f'VSAN plugin path accessible: {vsan_accessible}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2021-21972',
                                    'https://www.tenable.com/plugins/nessus/146983',
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
                description='No vCenter Server or VSAN plugin indicators detected'
            ))

        return results
