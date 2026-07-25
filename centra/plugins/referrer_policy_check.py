import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class ReferrerPolicyCheck(NaslPlugin):
    PLUGIN_ID = 1187
    NAME = 'Referrer-Policy Header Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = 'Checks the Referrer-Policy header configuration. A missing or permissive Referrer-Policy (unsafe-url, no-referrer-when-downgrade) can leak sensitive URL parameters, session tokens, or internal paths to external sites via the Referer header.'
    SOLUTION = 'Set Referrer-Policy: strict-origin-when-cross-origin or same-origin. Never use unsafe-url. Use no-referrer for sensitive pages.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    PERMISSIVE_POLICIES = ['unsafe-url', 'no-referrer-when-downgrade']
    STRICT_POLICIES = ['strict-origin-when-cross-origin', 'strict-origin', 'same-origin', 'no-referrer']

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
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nConnection: close\r\n\r\n'
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
                    header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                    policy = None
                    for line in header_section.split('\r\n'):
                        if line.lower().startswith('referrer-policy:'):
                            policy = line.split(':', 1)[1].strip()
                            break
                    if policy is None:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description='Referrer-Policy header is missing',
                            solution=self.SOLUTION,
                            evidence='No Referrer-Policy header found in HTTP response'
                        ))
                    elif any(p in policy.lower() for p in self.PERMISSIVE_POLICIES):
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description=f'Permissive Referrer-Policy: {policy}',
                            solution=self.SOLUTION,
                            evidence=f'Found permissive policy: {policy}'
                        ))
                    else:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=port_to_check,
                            description='No issues detected'
                        ))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description='No issues detected'
                ))
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No issues detected'))
        return results
