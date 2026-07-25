"""
Plugin 1272: gRPC Service Method Enumeration
==============================================
Enumerates gRPC service methods by probing common gRPC endpoints and
detecting gRPC-web protocol responses.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GRPCMethodEnumeration(NaslPlugin):
    PLUGIN_ID = 1272
    NAME = 'gRPC Service Method Enumeration'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Enumerates gRPC service methods by probing common gRPC endpoints and '
        'detecting gRPC-web protocol responses. Exposed gRPC services should '
        'be properly authenticated.'
    )
    SOLUTION = (
        'Implement proper authentication and authorization for all gRPC services. '
        'Use TLS for all gRPC connections. Restrict access to internal networks only.'
    )
    CVE = ['CVE-2024-7246']
    PORTS = [443, 8443, 50051, 8080, 9090]

    GRPC_PATHS = [
        '/',
        '/grpc.health.v1.Health/Check',
        '/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo',
        '/helloworld.Greeter/SayHello',
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

                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'

                for path in self.GRPC_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        grpc_body = b'\x00\x00\x00\x00\x00'
                        req = (
                            f'POST {path} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/grpc\r\n'
                            f'TE: trailers\r\n'
                            f'Content-Length: {len(grpc_body)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                        )
                        writer.write(req.encode() + grpc_body)
                        await writer.drain()

                        response = b''
                        try:
                            while True:
                                chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                                if not chunk:
                                    break
                                response += chunk
                                if len(response) > 16384:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()

                        header_section = response.split(b'\r\n\r\n', 1)[0] if b'\r\n\r\n' in response else response
                        headers_str = header_section.decode('utf-8', errors='ignore')

                        if 'application/grpc' in headers_str or 'grpc-web' in headers_str:
                            status_line = headers_str.split('\r\n')[0]
                            is_accessible = '200' in status_line
                            details = f'gRPC service detected at {path}'
                            if is_accessible:
                                details += ' - service responded (may be accessible)'
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='medium',
                                description=f'gRPC service detected at {path}',
                                solution=self.SOLUTION,
                                evidence=details,
                                references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-7246']
                            ))
                            break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if results:
                    break

                if not results:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        req = (
                            f'GET / HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/grpc\r\n'
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
                                if len(response) > 16384:
                                    break
                        except asyncio.TimeoutError:
                            pass
                        writer.close()
                        await writer.wait_closed()

                        header_section = response.split(b'\r\n\r\n', 1)[0] if b'\r\n\r\n' in response else response
                        headers_str = header_section.decode('utf-8', errors='ignore')

                        if 'application/grpc' in headers_str:
                            results.append(PluginResult(
                                vulnerable=True,
                                target=target,
                                port=port_to_check,
                                cvss_score=self.CVSS_SCORE,
                                severity='info',
                                description='gRPC protocol detected via content type header',
                                solution=self.SOLUTION,
                                evidence='gRPC protocol detected via content type header',
                                references=['https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-7246']
                            ))
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No gRPC services detected on checked ports'
            ))

        return results
