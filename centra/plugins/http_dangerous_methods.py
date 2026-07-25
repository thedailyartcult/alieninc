"""
Plugin 1181: HTTP Dangerous Methods Detection
===============================================
Detects dangerous HTTP methods (PUT, DELETE, PATCH, TRACE, CONNECT,
OPTIONS) enabled on the web server.
"""
import asyncio
import ssl
import uuid

from plugins import NaslPlugin, PluginResult


class HttpDangerousMethods(NaslPlugin):
    PLUGIN_ID = 1181
    NAME = 'HTTP Dangerous Methods Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Detects dangerous HTTP methods (PUT, DELETE, PATCH, TRACE, CONNECT, '
        'OPTIONS) enabled on the web server. Dangerous methods can allow '
        'attackers to modify, delete, or upload files. TRACE method enables '
        'XST (Cross-Site Tracing) attacks.'
    )
    SOLUTION = (
        'Disable unnecessary HTTP methods. Use Allow header to restrict '
        'methods to GET, POST, HEAD only. Authenticate all write operations.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    DANGEROUS_METHODS = ['PUT', 'DELETE', 'PATCH', 'TRACE', 'CONNECT', 'OPTIONS']

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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                allowed_methods = await self._get_allowed_methods(
                    target, port_to_check, ctx, host_header
                )

                dangerous_enabled = []
                for method in self.DANGEROUS_METHODS:
                    if method in allowed_methods:
                        if method == 'PUT':
                            status = await self._test_put(target, port_to_check, ctx, host_header)
                            if status and status < 500:
                                dangerous_enabled.append(method)
                        elif method == 'DELETE':
                            status = await self._test_delete(target, port_to_check, ctx, host_header)
                            if status and status < 500:
                                dangerous_enabled.append(method)
                        elif method == 'TRACE':
                            status = await self._test_method(target, port_to_check, ctx, host_header, 'TRACE', '/')
                            if status and status < 500:
                                dangerous_enabled.append(method)
                        elif method == 'PATCH':
                            status = await self._test_patch(target, port_to_check, ctx, host_header)
                            if status and status < 500:
                                dangerous_enabled.append(method)
                        elif method == 'CONNECT':
                            dangerous_enabled.append(method)
                        elif method == 'OPTIONS':
                            dangerous_enabled.append(method)

                if dangerous_enabled:
                    results.append(PluginResult(
                        vulnerable=True,
                        target=target,
                        port=port_to_check,
                        cvss_score=self.CVSS_SCORE,
                        severity='high',
                        description=(
                            f'Dangerous HTTP methods enabled: {", ".join(dangerous_enabled)}. '
                            f'Methods allowed: {", ".join(allowed_methods)}'
                        ),
                        solution=self.SOLUTION,
                        evidence=f'Enabled dangerous methods: {", ".join(dangerous_enabled)}. All allowed: {", ".join(allowed_methods)}',
                        references=[
                            'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/06-Test_HTTP_Methods',
                            'https://portswigger.net/kb/issues/00400300_http-methods-enabled',
                        ]
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No dangerous HTTP methods detected on checked ports'
            ))

        return results

    async def _get_allowed_methods(self, target: str, port: int, ctx, host_header: str) -> list[str]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            req = (
                f'OPTIONS / HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: Centra/1.0\r\n'
                f'Connection: close\r\n\r\n'
            )
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 8192:
                    break
            writer.close()
            await writer.wait_closed()

            header_section = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
            for line in header_section.split('\r\n'):
                if line.lower().startswith('allow:'):
                    methods = line.split(':', 1)[1].strip()
                    return [m.strip().upper() for m in methods.split(',')]
                if line.lower().startswith('public:'):
                    methods = line.split(':', 1)[1].strip()
                    return [m.strip().upper() for m in methods.split(',')]
        except Exception:
            pass
        return []

    async def _test_put(self, target: str, port: int, ctx, host_header: str) -> int | None:
        test_file = f'/centra_test_{uuid.uuid4().hex[:8]}.txt'
        return await self._send_method(target, port, ctx, host_header, 'PUT', test_file, 'test')

    async def _test_delete(self, target: str, port: int, ctx, host_header: str) -> int | None:
        return await self._send_method(target, port, ctx, host_header, 'DELETE', '/nonexistent_test_file.html')

    async def _test_patch(self, target: str, port: int, ctx, host_header: str) -> int | None:
        return await self._send_method(target, port, ctx, host_header, 'PATCH', '/', 'test')

    async def _test_method(self, target: str, port: int, ctx, host_header: str,
                           method: str, path: str) -> int | None:
        return await self._send_method(target, port, ctx, host_header, method, path)

    async def _send_method(self, target: str, port: int, ctx, host_header: str,
                           method: str, path: str, body: str | None = None) -> int | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )
            if body is not None:
                req = (
                    f'{method} {path} HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    f'Connection: close\r\n\r\n{body}'
                )
            else:
                req = (
                    f'{method} {path} HTTP/1.1\r\n'
                    f'Host: {host_header}\r\n'
                    f'User-Agent: Centra/1.0\r\n'
                    f'Connection: close\r\n\r\n'
                )
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                if not chunk:
                    break
                response += chunk
                if len(response) > 8192:
                    break
            writer.close()
            await writer.wait_closed()

            status_line = response.split(b'\r\n', 1)[0].decode('utf-8', errors='ignore')
            if ' ' in status_line:
                parts = status_line.split(' ')
                if len(parts) >= 2:
                    try:
                        return int(parts[1])
                    except ValueError:
                        pass
        except Exception:
            pass
        return None
