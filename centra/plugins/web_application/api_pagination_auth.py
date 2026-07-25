import asyncio
import json
import ssl
from plugins import NaslPlugin, PluginResult

class ApiPaginationNoAuth(NaslPlugin):
    PLUGIN_ID = 1248
    NAME = 'API Pagination / Mass Data Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects API endpoints that expose pagination without proper authentication or with predictable/guessable IDs. Unauthenticated pagination can leak all records including user data, orders, or internal notes.'
    SOLUTION = 'Enforce authentication on all paginated endpoints. Use cursor-based pagination instead of offset-based. Throttle API requests. Return only necessary fields.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        endpoints = ['/api/users', '/api/items', '/api/orders', '/api/products', '/api/v1/data', '/api/records', '/api/customers', '/api/transactions']
        params = ['?page=1&limit=10', '?offset=0&limit=10', '?skip=0&take=10', '?_page=1&_limit=10']
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for ep in endpoints:
                if found: break
                for param in params:
                    try:
                        ctx = None
                        scheme = 'https' if port_to_check in (443, 8443) else 'http'
                        if scheme == 'https':
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        path = ep + param
                        host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()
                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk: break
                                response += chunk
                                if len(response) > 16384: break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()
                        if response:
                            header_end = response.find(b'\r\n\r\n')
                            if header_end != -1:
                                body = response[header_end+4:]
                                status = int(response.split(b'\r\n')[0].split(b' ')[1])
                                if status == 200 and body.strip():
                                    try:
                                        data = json.loads(body.decode())
                                        if isinstance(data, list) and len(data) > 0:
                                            results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Unauthenticated pagination at {path} returned {len(data)} records.'))
                                            found = True; break
                                        if isinstance(data, dict):
                                            for k in ('data', 'items', 'records', 'results', 'rows', 'content'):
                                                if k in data and isinstance(data[k], list) and len(data[k]) > 0:
                                                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Unauthenticated pagination at {path} returned {len(data[k])} records in "{k}".'))
                                                    found = True; break
                                            if found: break
                                    except (json.JSONDecodeError, UnicodeDecodeError):
                                        pass
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No unauthenticated pagination found'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
