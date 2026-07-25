import asyncio
import json
import ssl
from plugins import NaslPlugin, PluginResult

class ApiSchemaFuzzing(NaslPlugin):
    PLUGIN_ID = 1249
    NAME = 'API Schema Validation / Mass Assignment Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Fuzzes API endpoints with unexpected data types, extra fields, and malformed input to detect schema validation weaknesses. Tests for missing input validation by sending negative numbers, oversized strings, special characters, and unexpected field types.'
    SOLUTION = 'Use strict input validation with schema definitions. Reject unexpected fields. Set maximum string lengths and numeric ranges. Use library-based validation libraries.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        endpoints = ['/api/users', '/api/items', '/api/orders', '/api/products', '/api/login', '/api/register', '/api/v1/data']
        payloads = [
            json.dumps({'name': 'test', 'price': -1, 'quantity': 0, 'role': 'admin', 'is_admin': True}),
            json.dumps({'name': 'A' * 5000, 'email': 'test@test.com'}),
            json.dumps({'__proto__': {'admin': True}, 'constructor': {'prototype': {'admin': True}}}),
            json.dumps({'id': None, 'name': '\x00null', 'price': 999999999999999999999999999999}),
            json.dumps({'name': '<script>alert(1)</script>', 'email': "' OR '1'='1"}),
        ]
        for port_to_check in (self.PORTS if port is None else [port]):
            for ep in endpoints:
                for payload in payloads:
                    try:
                        ctx = None
                        scheme = 'https' if port_to_check in (443, 8443) else 'http'
                        if scheme == 'https':
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                        req = f'POST {ep} HTTP/1.1\r\nHost: {host_header}\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n{payload}'
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
                            status = int(response.split(b'\r\n')[0].split(b' ')[1])
                            body = response[response.find(b'\r\n\r\n')+4:].decode(errors='replace')
                            if status in (200, 201, 202) and not any(e in body.lower() for e in ['error', 'invalid', 'required', 'validation']):
                                results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'API {ep} accepted fuzzed payload (status {status}). Possible mass assignment / missing validation.'))
                                break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                else:
                    continue
                break
            else:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No schema validation weakness detected'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
