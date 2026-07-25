"""
Plugin 1151: Cloud Metadata Service Detection
================================================
Tests for access to cloud metadata endpoints via SSRF-like probes.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class CloudMetadataDetection(NaslPlugin):
    PLUGIN_ID = 1151
    NAME = 'Cloud Metadata Service Detection'
    FAMILY = 'Misc.'
    CVSS_SCORE = 8.6
    DESCRIPTION = (
        'Tests for access to cloud metadata endpoints that could be used in SSRF '
        'attacks. Probes well-known cloud provider metadata IPs (169.254.169.254 '
        'for AWS/GCP/Azure, 100.100.100.200 for Alibaba) via various HTTP headers '
        'and parameters that might trigger server-side requests.'
    )
    SOLUTION = (
        'Block access to 169.254.169.254 and other metadata IPs. Use IMDSv2 with '
        'session tokens on AWS. Implement network-level protections.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    METADATA_IPS = [
        '169.254.169.254',
        '100.100.100.200',
    ]

    METADATA_PATHS = [
        '/',
        '/latest/meta-data/',
        '/latest/user-data/',
        '/metadata/instance?api-version=2021-02-01',
        '/computeMetadata/v1/instance/',
    ]

    SSRF_TEST_HEADERS = [
        'X-Forwarded-For',
        'X-Forwarded-Host',
        'X-Real-IP',
        'Forwarded',
        'X-Forwarded-Proto',
        'Client-IP',
        'X-Originating-IP',
        'X-Remote-IP',
        'X-Remote-Addr',
        'True-Client-IP',
        'X-Client-IP',
        'X-Host',
        'X-Original-URL',
        'X-Rewrite-URL',
        'X-Custom-IP-Authorization',
    ]

    METADATA_SIGNATURES = {
        'aws': ['ami-id', 'instance-id', 'public-keys', 'security-credentials', 'iam/'],
        'gcp': ['project/', 'instance/', 'computeMetadata', 'machineType'],
        'azure': ['compute/', 'network/', 'subscriptionId', 'resourceGroupName'],
        'alibaba': ['instance-id', 'region-id', 'zone-id', 'image-id'],
        'digitalocean': ['droplet_id', 'hostname', 'vendor_data'],
    }

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        for port_to_check in (self.PORTS if port is None else [port]):
            for metadata_ip in self.METADATA_IPS:
                try:
                    found = await self._probe_metadata_target(target, port_to_check, metadata_ip)
                    if found:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='critical',
                            description=f'Cloud metadata service accessible via SSRF at {metadata_ip}',
                            solution=self.SOLUTION,
                            evidence=f'Successfully accessed {metadata_ip} metadata endpoint',
                            references=[
                                'https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html',
                                'https://docs.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service',
                                'https://cloud.google.com/compute/docs/metadata',
                            ]
                        ))
                        return results

                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No cloud metadata service accessible via tested endpoints'
            ))

        return results

    async def _probe_metadata_target(self, target: str, port: int, metadata_ip: str) -> bool:
        for metadata_path in self.METADATA_PATHS:
            try:
                scheme = 'https' if port in (443, 8443) else 'http'
                ctx = None
                if scheme == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                for header_name in self.SSRF_TEST_HEADERS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port, ssl=ctx),
                            timeout=5
                        )

                        host_header = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host_header = 'alieninc.tech'

                        ssrf_url = f'http://{metadata_ip}{metadata_path}'
                        req = (
                            f'GET {metadata_path} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'{header_name}: {metadata_ip}\r\n'
                            f'X-Metadata-Request: true\r\n'
                            f'Metadata: true\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                        )
                        writer.write(req.encode())
                        await writer.drain()

                        response = b''
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 65536:
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

                        if status_code != 200:
                            continue

                        body_text = body.decode('utf-8', errors='ignore')[:4096]

                        if self._is_metadata_response(body_text):
                            return True

                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                        pass

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

        return False

    def _is_metadata_response(self, body: str) -> bool:
        for cloud, sigs in self.METADATA_SIGNATURES.items():
            for sig in sigs:
                if sig in body.lower():
                    return True

        if re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', body):
            return True

        if 'instance' in body.lower() and any(x in body.lower() for x in ('id', 'name', 'zone', 'region')):
            return True

        return False
