import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class SamlAssertionDetection(NaslPlugin):
    PLUGIN_ID = 1219
    NAME = 'SAML Assertion Manipulation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = 'Detects SAML assertion manipulation vulnerabilities including XML signature wrapping, missing signature validation, and arbitrary assertion injection. SAML vulnerabilities allow attackers to forge authentication assertions and impersonate any user.'
    SOLUTION = 'Validate SAML assertions strictly. Verify XML digital signatures. Use the latest SAML libraries with proper security defaults. Validate all SAML fields against expected values.'
    CVE = ['CVE-2017-11427', 'CVE-2018-0489']
    PORTS = [80, 443, 8080, 8443]

    SAML_PATHS = [
        '/SAML', '/auth/saml', '/saml/acs', '/sso/saml',
        '/saml', '/auth/sso/saml', '/saml/SSO', '/SAML/AssertionConsumerService',
        '/api/auth/saml', '/saml2', '/auth/saml2',
    ]

    SAML_PAYLOADS = [
        '<samlp:Response><saml:Assertion><saml:Subject><saml:NameID>admin@test.com</saml:NameID></saml:Subject></saml:Assertion></samlp:Response>',
        '<saml:Assertion><saml:Subject><saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">admin@test.com</saml:NameID></saml:Subject></saml:Assertion>',
        '<samlp:Response><saml:Assertion><saml:AttributeStatement><saml:Attribute Name="Role"><saml:AttributeValue>admin</saml:AttributeValue></saml:Attribute></saml:AttributeStatement></saml:Assertion></samlp:Response>',
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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target

                for path in self.SAML_PATHS:
                    for payload in self.SAML_PAYLOADS:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                            )
                            content_length = len(payload.encode())
                            req = (
                                f'POST {path} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Content-Type: text/xml\r\n'
                                f'Content-Length: {content_length}\r\n'
                                f'Connection: close\r\n\r\n'
                                f'{payload}'
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
                            writer.close()
                            await writer.wait_closed()

                            if response:
                                status_line = response.split(b'\r\n', 1)[0].decode(errors='ignore')
                                body = response.split(b'\r\n\r\n', 1)[1].decode(errors='ignore') if b'\r\n\r\n' in response else ''
                                if '200' in status_line or '302' in status_line:
                                    results.append(PluginResult(
                                        vulnerable=True,
                                        target=target,
                                        port=port_to_check,
                                        cvss_score=self.CVSS_SCORE,
                                        severity='critical',
                                        description=f'SAML endpoint {path} accepted manipulated SAML assertion payload',
                                        solution=self.SOLUTION,
                                        evidence=f'SAML payload accepted at {path} - status: {status_line.strip()}',
                                        references=[
                                            'https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2017-11427',
                                            'https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2018-0489',
                                            'https://owasp.org/www-community/attacks/SAML_Attack_Cheat_Sheet',
                                        ]
                                    ))
                                    break
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
                    if results:
                        break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No SAML assertion manipulation detected'))
        return results
