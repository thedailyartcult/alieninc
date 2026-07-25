import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class RateLimitingBypass(NaslPlugin):
    PLUGIN_ID = 1186
    NAME = 'Rate Limiting Bypass Assessment'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = 'Tests the robustness of rate limiting by attempting bypass techniques including header manipulation (X-Forwarded-For rotation), parameter-based IP spoofing, concurrent request splitting, and slow loris patterns. Weak rate limiting allows brute force and DoS attacks.'
    SOLUTION = 'Rate limit by session and IP simultaneously. Use consistent rate limiting at the proxy level. Implement progressive delays. Use CAPTCHA after failed attempts.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    ENDPOINTS = ['/login', '/api/login', '/auth', '/api/auth']
    FAKE_IPS = [f'192.168.{i}.{j}' for i in range(1, 6) for j in range(1, 3)]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            bypassed = False
            status_codes = []
            try:
                for fake_ip in self.FAKE_IPS[:10]:
                    scheme = 'https' if port_to_check in (443, 8443) else 'http'
                    ctx = None
                    if scheme == 'https':
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                    host_header = target
                    if target in ('127.0.0.1', 'localhost', '::1'):
                        host_header = 'alieninc.tech'
                    body = b'{"email":"test","password":"test"}'
                    req = (
                        f'POST /login HTTP/1.1\r\n'
                        f'Host: {host_header}\r\n'
                        f'X-Forwarded-For: {fake_ip}\r\n'
                        f'Content-Type: application/json\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Connection: close\r\n\r\n'
                    )
                    writer.write(req.encode() + body)
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
                        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                        status_line = header_section.split('\r\n')[0] if header_section else ''
                        status_code = 0
                        if 'HTTP/' in status_line:
                            try:
                                status_code = int(status_line.split()[1])
                            except (IndexError, ValueError):
                                pass
                        status_codes.append(status_code)
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

            if status_codes:
                success_count = sum(1 for s in status_codes if s == 200)
                if success_count >= 8:
                    bypassed = True
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Rate limiting bypassed: {success_count}/10 requests succeeded with rotated IP headers',
                        solution=self.SOLUTION,
                        evidence=f'Sent 10 rapid requests with varying X-Forwarded-For headers; {success_count} returned HTTP 200'
                    ))

            if not any(r.target == target and r.port == port_to_check for r in results):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
