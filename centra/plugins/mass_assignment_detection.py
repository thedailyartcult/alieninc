import asyncio
import ssl
import json
from plugins import NaslPlugin, PluginResult

class MassAssignmentDetection(NaslPlugin):
    PLUGIN_ID = 1212
    NAME = 'Mass Assignment / Auto-Binding Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects mass assignment (auto-binding) vulnerabilities by sending unexpected parameters (is_admin, role, admin, permissions, verified, balance) to API endpoints. If the server auto-binds request parameters to objects, attackers can modify protected fields.'
    SOLUTION = 'Use DTOs (Data Transfer Objects) for input binding. Whitelist allowed parameters. Avoid auto-binding request parameters directly to database models.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        endpoints = ['/api/user', '/api/users', '/api/profile', '/api/register', '/api/update', '/user/update', '/admin/user/update']
        sensitive_params = {'is_admin': 'true', 'role': 'admin', 'admin': 'true', 'permissions': 'all', 'verified': 'true', 'balance': '1000000'}
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

                for endpoint in endpoints:
                    body_data = {**sensitive_params, 'name': 'test', 'email': 'test@test.com'}
                    body = json.dumps(body_data)
                    req = (
                        f'POST {endpoint} HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'Content-Type: application/json\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n'
                        f'{body}'
                    )
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    writer.write(req.encode())
                    await writer.drain()
                    resp = b''
                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk: break
                            resp += chunk
                            if len(resp) > 8192: break
                    except asyncio.TimeoutError:
                        pass
                    writer.close()
                    await writer.wait_closed()

                    if resp:
                        body = resp.split(b'\r\n\r\n', 1)[-1] if b'\r\n\r\n' in resp else resp
                        for key, val in sensitive_params.items():
                            if key.encode() in body.lower() and val.encode() in body.lower():
                                results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Mass assignment possible at {endpoint}: {key}={val} reflected in response'))
                                return results
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No mass assignment detected'))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='Connection failed'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
