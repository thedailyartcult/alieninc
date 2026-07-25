"""
Plugin 1275: Zoho ManageEngine SAML RCE (CVE-2022-47966)
=========================================================
Zoho ManageEngine on-premise products (including ADSelfService Plus,
ServiceDesk Plus, and others) are vulnerable to a critical
pre-authentication remote code execution via SAML SSO.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class ManageEngineRCE47966(NaslPlugin):
    PLUGIN_ID = 1275
    NAME = 'Zoho ManageEngine SAML RCE (CVE-2022-47966)'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Zoho ManageEngine on-premise products (including ADSelfService Plus, '
        'ServiceDesk Plus, and others) are vulnerable to a critical '
        'pre-authentication remote code execution via SAML SSO. An unauthenticated '
        'attacker can execute arbitrary code by exploiting Apache Santuario '
        'XML security.'
    )
    SOLUTION = (
        'Upgrade ManageEngine products to the latest builds. For ADSelfService '
        'Plus, upgrade to build 6210 or later.'
    )
    CVE = ['CVE-2022-47966']
    PORTS = [80, 443, 8080, 8443]

    ENDPOINTS = [
        '/', '/saml/SSO', '/SamlResponseServlet',
        '/webclient/', '/mfa/', '/RestAPI/',
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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for endpoint in self.ENDPOINTS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        req = (
                            f'GET {endpoint} HTTP/1.1\r\n'
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
                                if len(response) > 16384:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()

                        header_section = response.split(b'\r\n\r\n', 1)[0] if b'\r\n\r\n' in response else response
                        body = response.split(b'\r\n\r\n', 1)
                        body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''
                        headers_str = header_section.decode('utf-8', errors='ignore')

                        server_header = ''
                        for line in headers_str.split('\r\n'):
                            if line.lower().startswith('server:'):
                                server_header = line.split(':', 1)[1].strip()
                                break

                        if any(x in body_text for x in ['ManageEngine', 'ADSelfService', 'Zoho Corp', 'ZOHO Corp', 'manageengine']):
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='critical',
                                description=f'Zoho ManageEngine product detected at {endpoint}',
                                solution=self.SOLUTION,
                                evidence=f'ManageEngine product detected. Server: {server_header or "N/A"}',
                                references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2022-47966']
                            ))
                            break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if results:
                    break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ManageEngine product detected on checked ports'
            ))

        return results
