import asyncio
import ssl
from plugins import NaslPlugin, PluginResult


class PermissionsPolicyCheck(NaslPlugin):
    PLUGIN_ID = 1188
    NAME = 'Permissions-Policy / Feature-Policy Security Check'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 3.7
    DESCRIPTION = 'Checks the Permissions-Policy (formerly Feature-Policy) header configuration. A missing or permissive permissions policy allows websites to access powerful browser APIs (camera, microphone, geolocation, sensors) without restriction.'
    SOLUTION = 'Implement a restrictive Permissions-Policy header disabling unused APIs. Use interest-cohort=() to opt out of FLoC. Example: Permissions-Policy: camera=(), microphone=(), geolocation=()'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

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
                    permissions_policy = None
                    feature_policy = None
                    for line in header_section.split('\r\n'):
                        if line.lower().startswith('permissions-policy:'):
                            permissions_policy = line.split(':', 1)[1].strip()
                        if line.lower().startswith('feature-policy:'):
                            feature_policy = line.split(':', 1)[1].strip()
                    if permissions_policy is None and feature_policy is None:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description='Permissions-Policy header is missing',
                            solution=self.SOLUTION,
                            evidence='No Permissions-Policy or Feature-Policy header found'
                        ))
                    elif permissions_policy and 'camera=()' not in permissions_policy and 'microphone=()' not in permissions_policy:
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description='Permissions-Policy is not restrictive enough',
                            solution=self.SOLUTION,
                            evidence=f'Current policy: {permissions_policy}'
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
