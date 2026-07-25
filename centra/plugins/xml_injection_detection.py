import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class XmlInjectionDetection(NaslPlugin):
    PLUGIN_ID = 1198
    NAME = 'XML Injection / XPATH Injection Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 8.6
    DESCRIPTION = 'Detects XML injection and XPATH injection vulnerabilities by injecting XML metacharacters and XPATH expressions into parameters. XML injection can break XML parsing logic, while XPATH injection can extract data from XML databases.'
    SOLUTION = 'Escape XML special characters (<, >, &, \x27, \x22). Use parameterized XPATH queries. Validate XML input against a schema. Disable external entity loading.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    INJECTION_PAYLOADS = [
        {'name': 'xml_meta_open', 'payload': '<'},
        {'name': 'xml_meta_close', 'payload': '>'},
        {'name': 'xml_ampersand', 'payload': '&'},
        {'name': 'xml_single_quote', 'payload': "'"},
        {'name': 'xml_double_quote', 'payload': '"'},
        {'name': 'xpath_or', 'payload': "' or '1'='1"},
        {'name': 'xpath_and', 'payload': "' and '1'='1"},
        {'name': 'xpath_union', 'payload': "' | //*"},
        {'name': 'xpath_parent', 'payload': "' or 1=1 or '"},
        {'name': 'xpath_comment', 'payload': "'--"},
    ]

    INJECTION_PARAMS = ['search', 'q', 'id', 'page', 'name', 'user', 'filter', 'category', 'xml', 'data']

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

                for payload in self.INJECTION_PAYLOADS:
                    for param in self.INJECTION_PARAMS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            qs = f'{param}={payload["payload"]}'
                            req = f'GET /search?{qs} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                            writer.write(req.encode())
                            await writer.drain()

                            response = b''
                            try:
                                while True:
                                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                    if not chunk: break
                                    response += chunk
                                    if len(response) > 8192: break
                            except asyncio.TimeoutError:
                                pass

                            writer.close()
                            await writer.wait_closed()

                            if response:
                                body_lower = response.lower()
                                xml_error_indicators = [
                                    b'xml', b'xpath', b'xpathException', b'org.xml',
                                    b'saxparse', b'documentbuilder', b'xpointer',
                                    b'invalid xml', b'xml parse', b'malformed xml',
                                    b'xpath expression', b'unexpected token', b'system.xml',
                                ]
                                if any(ind in body_lower for ind in xml_error_indicators):
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='high',
                                        description=f'XML/XPATH injection detected with {payload["name"]} payload in parameter {param}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload: {payload["name"]} ({payload["payload"]}), parameter: {param}',
                                        references=['https://owasp.org/www-community/attacks/XML_Injection', 'https://owasp.org/www-community/attacks/XPATH_Injection']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No XML/XPATH injection vulnerabilities detected'))
        return results
