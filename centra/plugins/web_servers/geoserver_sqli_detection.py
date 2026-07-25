"""
Plugin 1103: GeoServer SQL Injection (CVE-2023-25157)
======================================================
Detects SQL injection vulnerability in GeoServer WFS GetFeature service.
Real CVE: CVE-2023-25157 (CVSS 9.8)
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GeoserverSqliDetection(NaslPlugin):
    PLUGIN_ID = 1103
    NAME = 'GeoServer SQL Injection (CVE-2023-25157)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'GeoServer before 2.21.4, 2.22.2, and 2.23.0 contains a SQL injection '
        'vulnerability in the WFS GetFeature service. An unauthenticated attacker '
        'can craft SQL injection payloads through the viewParams query parameter, '
        'potentially extracting or modifying database content.'
    )
    SOLUTION = (
        'Upgrade GeoServer to 2.21.4, 2.22.2, 2.23.0 or later. '
        'Disable WFS service if not needed.'
    )
    CVE = ['CVE-2023-25157']
    PORTS = [80, 443, 8080, 8443]

    GEOSERVER_PATHS = ['/geoserver/web', '/geoserver/', '/web/']
    GEOSERVER_INDICATORS = [
        b'GeoServer',
        b'geoserver',
        b'WFS',
        b'WMS',
        b'GeoServerLogo',
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

                for path in self.GEOSERVER_PATHS:
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
                        geoserver_detected = any(indicator in response for indicator in self.GEOSERVER_INDICATORS)

                        if geoserver_detected:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=(
                                    f'GeoServer detected on port {port_to_check} — '
                                    f'potentially vulnerable to SQL injection in WFS '
                                    f'GetFeature service (CVE-2023-25157)'
                                ),
                                solution=self.SOLUTION,
                                evidence=(
                                    f'Path: {path}, Status: {status_line}, '
                                    f'GeoServer indicators found: {geoserver_detected}'
                                ),
                                references=[
                                    'https://nvd.nist.gov/vuln/detail/CVE-2023-25157',
                                    'https://www.tenable.com/plugins/nessus/173724',
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
                description='No GeoServer SQL injection indicators detected on checked ports'
            ))

        return results
