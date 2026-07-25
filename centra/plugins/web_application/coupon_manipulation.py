import asyncio
import json
import ssl
from plugins import NaslPlugin, PluginResult

class CouponManipulation(NaslPlugin):
    PLUGIN_ID = 1251
    NAME = 'Coupon / Price Manipulation Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects business logic vulnerabilities in coupon, discount, and pricing functionality. Tests for coupon code reuse, negative quantity manipulation, price override via request modification, and integer overflow in pricing operations.'
    SOLUTION = 'Calculate prices server-side only. Validate coupon usage limits server-side. Do not rely on client-side price values. Use idempotency keys for orders. Implement strict validation on numeric fields.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        payloads = [
            ('POST', '/cart/add', json.dumps({'product_id': 1, 'quantity': -1, 'price': 0})),
            ('POST', '/cart/add', json.dumps({'product_id': 1, 'quantity': 999999, 'price': -100})),
            ('POST', '/checkout/apply-coupon', json.dumps({'code': 'FREESHIP', 'order_total': 999999})),
            ('POST', '/checkout/apply-coupon', json.dumps({'code': 'FREESHIP', 'order_total': 0})),
            ('POST', '/checkout/apply-coupon', json.dumps({'code': 'FREESHIP', 'order_total': -500})),
            ('POST', '/api/order', json.dumps({'items': [{'id': 1, 'price': 0.01, 'quantity': 100}], 'coupon': 'REUSE', 'use_coupon': True})),
            ('POST', '/checkout', json.dumps({'price_override': 0, 'currency': 'USD', 'quantity': -999999999999})),
        ]
        endpoints_to_test = ['/cart', '/checkout', '/cart/add', '/checkout/apply-coupon', '/api/order', '/api/coupon', '/api/checkout']
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for method, ep, body in payloads:
                try:
                    ctx = None
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                    req = f'{method} {ep} HTTP/1.1\r\nHost: {host_header}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}'
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
                    if status in (200, 201, 202, 302) and status != 400:
                        results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'{method} {ep} with manipulated data returned {status}. Possible pricing manipulation vulnerability.'))
                        found = True
                        break
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                    pass
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No coupon/price manipulation vulnerability detected'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
