import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class MultistepBypass(NaslPlugin):
    PLUGIN_ID = 1252
    NAME = 'Multi-Step Process Bypass Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = 'Detects multi-step process bypass vulnerabilities by directly accessing later steps in a workflow without completing earlier steps (e.g., directly accessing /checkout/payment without going through /checkout/cart). Tests checkout flows, registration flows, and multi-page forms.'
    SOLUTION = 'Validate session state at every step. Do not rely on client-side navigation for process flow. Use CSRF tokens for each step. Maintain required state server-side.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        workflows = [
            ('checkout', ['/checkout/cart', '/checkout/shipping', '/checkout/payment', '/checkout/review', '/checkout/confirm']),
            ('registration', ['/register', '/register/verify', '/register/complete', '/register/profile']),
            ('admin', ['/admin/login', '/admin/dashboard', '/admin/users', '/admin/settings']),
            ('password_reset', ['/reset-password', '/reset-password/confirm', '/reset-password/complete']),
            ('onboarding', ['/onboarding/welcome', '/onboarding/profile', '/onboarding/done']),
        ]
        for port_to_check in (self.PORTS if port is None else [port]):
            found = False
            for flow_name, steps in workflows:
                if found: break
                for step in steps[1:]:
                    try:
                        ctx = None
                        scheme = 'https' if port_to_check in (443, 8443) else 'http'
                        if scheme == 'https':
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                        host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                        req = f'GET {step} HTTP/1.1\r\nHost: {host_header}\r\nCookie: session=test\r\nConnection: close\r\n\r\n'
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
                            body_lower = response[response.find(b'\r\n\r\n')+4:].decode(errors='replace').lower()
                            if status in (200, 302) and not any(e in body_lower for e in ['login', 'sign in', 'unauthorized', 'forbidden', 'access denied', 'redirect']):
                                results.append(PluginResult(vulnerable=True, target=target, port=port_to_check, description=f'Direct access to {flow_name} step {step} returned {status}. Multi-step process bypass possible.'))
                                found = True
                                break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
            if not found:
                results.append(PluginResult(vulnerable=False, target=target, port=port_to_check, description='No multi-step bypass detected'))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
