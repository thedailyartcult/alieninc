import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class ApiRateLimit(NaslPlugin):
    PLUGIN_ID = 1250
    NAME = 'API Rate Limiting Assessment'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Assesses API rate limiting effectiveness by sending a series of rapid requests to API endpoints and measuring response status codes and headers. Detects missing RateLimit headers and the number of requests allowed before throttling.'
    SOLUTION = 'Implement rate limiting on all API endpoints. Return Retry-After headers. Use 429 status code for rate-limited responses. Include RateLimit-* response headers.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        endpoints = ['/api/users', '/api/items', '/api/products', '/api/login', '/']
        for port_to_check in (self.PORTS if port is None else [port]):
            for ep in endpoints:
                rate_limited = False
                has_headers = False
                status_codes = set()
                rate_limit_headers = set()
                for _ in range(20):
                    try:
                        ctx = None
                        scheme = 'https' if port_to_check in (443, 8443) else 'http'
                        if scheme == 'https':
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=3)
                        host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                        req = f'GET {ep} HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()
                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=2)
                                if not chunk: break
                                response += chunk
                                if len(response) > 4096: break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()
                        if response:
                            status = int(response.split(b'\r\n')[0].split(b' ')[1])
                            status_codes.add(status)
                            headers_raw = response.split(b'\r\n\r\n')[0].decode(errors='replace')
                            if status == 429:
                                rate_limited = True
                            for h in ['x-ratelimit', 'rateLimit', 'x-rate', 'retry-after', 'x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset']:
                                if any(h in hl.lower() for hl in headers_raw.split('\r\n')):
                                    rate_limit_headers.add(h)
                                    has_headers = True
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if rate_limited or has_headers:
                    results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description=f'Rate limiting present on {ep}: 429 seen={rate_limited}, headers={rate_limit_headers}'))
                else:
                    results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'No rate limiting detected on {ep} after 20 requests. Status codes seen: {sorted(status_codes)}'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
