"""
Plugin 1273: gRPC Reflection API Exposure
===========================================
Detects exposed gRPC Server Reflection API. When enabled in production,
reflection allows any client to discover all available gRPC services and
methods without authentication.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class GRPCReflectionDetection(NaslPlugin):
    PLUGIN_ID = 1273
    NAME = 'gRPC Reflection API Exposure'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects exposed gRPC Server Reflection API. When enabled in production, '
        'reflection allows any client to discover all available gRPC services '
        'and methods without authentication.'
    )
    SOLUTION = (
        'Disable gRPC reflection in production environments. If reflection is '
        'needed, restrict access to internal networks only and implement proper '
        'authentication.'
    )
    CVE = []
    PORTS = [443, 8443, 50051, 8080, 9090]

    REFLECTION_PATHS = [
        '/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo',
        '/grpc.reflection.v1.ServerReflection/ServerReflectionInfo',
    ]

    LIST_SERVICES_PAYLOAD = bytes.fromhex(
        '00000000100a14677270632e7265666c656374696f6e2e76311218677270632e'
        '7265666c656374696f6e2e76312e5365727665725265666c656374696f6e1207'
        '4c69737453657276696365731a0000000000'
    )

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

                for path in self.REFLECTION_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )
                        req = (
                            f'POST {path} HTTP/1.1\r\n'
                            f'Host: {host_header}\r\n'
                            f'Content-Type: application/grpc\r\n'
                            f'TE: trailers\r\n'
                            f'Content-Length: {len(self.LIST_SERVICES_PAYLOAD)}\r\n'
                            f'User-Agent: Centra/1.0\r\n'
                            f'Connection: close\r\n\r\n'
                        )
                        writer.write(req.encode() + self.LIST_SERVICES_PAYLOAD)
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
                        body = response.split(b'\r\n\r\n', 1)
                        body_text = body[1].decode('utf-8', errors='ignore') if len(body) > 1 else ''

                        status_line = headers_str.split('\r\n')[0]
                        status_code = 0
                        if ' ' in status_line:
                            try:
                                status_code = int(status_line.split(' ')[1])
                            except (IndexError, ValueError):
                                pass

                        if 'application/grpc' in headers_str and status_code in (200, 403):
                            if 'service' in body_text.lower() or 'grpc' in body_text.lower() or len(body_text) > 10:
                                results.append(PluginResult(
                                    vulnerable=True,
                                    target=target,
                                    port=port_to_check,
                                    cvss_score=self.CVSS_SCORE,
                                    severity='medium',
                                    description=f'gRPC Reflection API exposed at {path}',
                                    solution=self.SOLUTION,
                                    evidence=f'gRPC Reflection API exposed at {path}. All services can be enumerated.',
                                    references=[
                                        'https://github.com/grpc/grpc/blob/master/doc/server-reflection.md',
                                    ]
                                ))
                                break
                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass
                if results:
                    break

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No gRPC Reflection API detected on checked ports'
            ))

        return results
