"""
Plugin 1245: CORS Private Network Access Detection
===================================================
Detects CORS Private Network Access (PNA) configuration issues.
Tests if the server correctly handles preflight requests from
public origins targeting internal resources.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CorsPrivateNetworkAccessDetection(NaslPlugin):
    PLUGIN_ID = 1245
    NAME = 'CORS Private Network Access Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects CORS Private Network Access (PNA) configuration issues. PNA '
        'restricts requests from public websites to private network resources. '
        'Tests if the server correctly handles preflight requests from public '
        'origins targeting internal resources.'
    )
    SOLUTION = (
        'Implement Access-Control-Request-Private-Network: true preflight '
        'handling. Use resource timing headers. Consider removing unnecessary '
        'cross-origin access to private network resources.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    TEST_ORIGINS = [
        'https://evil.com',
        'https://attacker.net',
        'https://malicious.site',
        'null',
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
                host_header = 'alieninc.tech' if target in ('127.0.0.1', 'localhost', '::1') else target
                for origin in self.TEST_ORIGINS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                        )
                        req = (
                            f'OPTIONS / HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Origin: {origin}\r\n'
                            f'Access-Control-Request-Method: GET\r\n'
                            f'Access-Control-Request-Private-Network: true\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
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
                                if len(response) > 8192:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()
                        headers = response.split(b'\r\n\r\n')[0] if b'\r\n\r\n' in response else response
                        headers_text = headers.decode('utf-8', errors='ignore').lower()
                        if 'access-control-allow-private-network: true' in headers_text:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='medium',
                                description=(
                                    f'Server accepts PNA preflight from origin "{origin}" '
                                    f'and responds with Access-Control-Allow-Private-Network: true'
                                ),
                                solution=self.SOLUTION,
                                evidence=f'Requests from public origin {origin} are granted private network access',
                                references=[
                                    'https://wicg.github.io/private-network-access/',
                                    'https://developer.chrome.com/blog/private-network-access-update/',
                                ]
                            ))
                        else:
                            cors_origin = next(
                                (ln for ln in headers_text.split('\r\n') if 'access-control-allow-origin' in ln),
                                None
                            )
                            if cors_origin and ('*' in cors_origin or origin.replace('https://', '').replace('http://', '') in cors_origin):
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='medium',
                                    description=(
                                        f'Server allows CORS from origin "{origin}" but does not '
                                        f'enforce PNA restrictions'
                                    ),
                                    solution=self.SOLUTION,
                                    evidence=f'CORS headers: {cors_origin}, missing PNA validation',
                                    references=[
                                        'https://wicg.github.io/private-network-access/',
                                    ]
                                ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                    if results:
                        break
                if not results:
                    results.append(PluginResult(
                        vulnerable=False,
                        target=target,
                        port=port_to_check,
                        description='CORS Private Network Access appears properly configured'
                    ))
                    break
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No CORS PNA indicators detected'
            ))
        return results
