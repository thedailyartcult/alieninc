import asyncio
import ssl
from plugins import NaslPlugin, PluginResult

class HttpMethodTunneling(NaslPlugin):
    PLUGIN_ID = 1203
    NAME = 'HTTP Method Tunneling Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 6.1
    DESCRIPTION = 'Detects HTTP method tunneling via X-HTTP-Method-Override and similar headers that allow bypassing HTTP method restrictions. If the server honors these headers, an attacker can bypass access controls by tunneling dangerous methods through allowed ones.'
    SOLUTION = 'Restrict allowed HTTP methods. Disable X-HTTP-Method-Override and similar header processing. Validate the actual HTTP method, not the override header.'
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    OVERRIDE_HEADERS = [
        'X-HTTP-Method-Override',
        'X-HTTP-Method',
        'X-Method-Override',
        'X-HTTP-Method-Override-Original',
    ]

    OVERRIDE_METHODS = ['PUT', 'DELETE', 'PATCH', 'OPTIONS', 'TRACE', 'CONNECT']

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

                for header in self.OVERRIDE_HEADERS:
                    for method in self.OVERRIDE_METHODS:
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5)
                            host_header = target
                            if target in ('127.0.0.1', 'localhost', '::1'):
                                host_header = 'alieninc.tech'

                            req = (
                                f'POST /api/resource HTTP/1.1\r\n'
                                f'Host: {host_header}\r\n'
                                f'{header}: {method}\r\n'
                                f'Content-Length: 0\r\n'
                                f'Connection: close\r\n\r\n'
                            )
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
                                status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                                status_code = 0
                                parts = status_line.split(' ')
                                if len(parts) >= 2:
                                    try:
                                        status_code = int(parts[1])
                                    except ValueError:
                                        pass

                                if status_code not in (0, 405, 501, 400, 403, 404):
                                    results.append(PluginResult(
                                        vulnerable=True, target=target, port=port_to_check,
                                        cvss_score=self.CVSS_SCORE, severity='medium',
                                        description=f'HTTP method tunneling detected via {header}: {method} - server returned {status_code}',
                                        solution=self.SOLUTION,
                                        evidence=f'Header: {header}, override method: {method}, response status: {status_code}',
                                        references=['https://owasp.org/www-community/attacks/HTTP_Method_Override']
                                    ))
                        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                            pass
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0, description='No HTTP method tunneling vulnerabilities detected'))
        return results
