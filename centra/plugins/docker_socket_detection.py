"""
Plugin 1165: Docker Socket Exposure Detection
===============================================
Detects exposed Docker daemon sockets (TCP or UNIX socket mounted in web root).
"""
import asyncio
import json
import ssl

from plugins import NaslPlugin, PluginResult


class DockerSocketDetection(NaslPlugin):
    PLUGIN_ID = 1165
    NAME = 'Docker Socket Exposure Detection'
    FAMILY = 'Misc.'
    CVSS_SCORE = 9.1
    DESCRIPTION = (
        'Detects exposed Docker daemon sockets (TCP port 2375/2376 or UNIX '
        'socket mounted in web root). Exposed Docker sockets allow unauthenticated '
        'container management, leading to full host compromise.'
    )
    SOLUTION = (
        'Never expose Docker socket remotely without TLS authentication. Restrict '
        'socket access to admin users. Use firewall rules to block public access '
        'to Docker ports.'
    )
    PORTS = [2375, 2376, 80, 443, 8080, 8443]

    DOCKER_API_PATHS = [
        '/containers/json',
        '/version',
        '/info',
        '/images/json',
        '/_ping',
        '/containers/json?all=true',
        '/services',
        '/tasks',
        '/nodes',
    ]
    DOCKER_SOCK_PATHS = [
        '/var/run/docker.sock',
        '/run/docker.sock',
        '/docker.sock',
    ]

    async def check_target(self, target: str, port: int | None = None) -> list[PluginResult]:
        results = []
        for port_to_check in (self.PORTS if port is None else [port]):
            try:
                if port_to_check in (2375, 2376):
                    await self._check_docker_tcp(target, port_to_check, results)
                else:
                    await self._check_docker_web(target, port_to_check, results)
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results

    async def _check_docker_tcp(self, target: str, port: int, results: list):
        try:
            ctx = None
            if port == 2376:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port, ssl=ctx), timeout=5
            )

            for api_path in self.DOCKER_API_PATHS[:3]:
                req = f'GET {api_path} HTTP/1.1\r\nHost: localhost\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                writer.write(req.encode())
                await writer.drain()

                response = b''
                while True:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 16384:
                        break

                body = response.split(b'\r\n\r\n', 1)
                if len(body) > 1:
                    body_text = body[1].decode('utf-8', errors='ignore')
                    try:
                        data = json.loads(body_text)
                        if isinstance(data, (dict, list)):
                            docker_info = ''
                            if isinstance(data, dict):
                                docker_info = f'Docker version: {data.get("Version", "unknown")}' if api_path == '/version' else f'Containers: {data.get("Containers", "unknown")}' if api_path == '/info' else f'Items: {len(data)}'
                            elif isinstance(data, list):
                                docker_info = f'Containers running: {len(data)}'

                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port,
                                cvss_score=self.CVSS_SCORE, severity='critical',
                                description='Docker daemon TCP socket exposed without authentication',
                                solution=self.SOLUTION,
                                evidence=f'Docker API accessible on port {port} via {api_path}: {docker_info}',
                                references=[
                                    'https://www.tenable.com/plugins/nessus/109093',
                                    'https://docs.docker.com/engine/security/',
                                ]
                            ))
                            writer.close()
                            await writer.wait_closed()
                            return
                    except json.JSONDecodeError:
                        pass

                writer.close()
                await writer.wait_closed()
                return

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
            pass

    async def _check_docker_web(self, target: str, port: int, results: list):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'

            for sock_path in self.DOCKER_SOCK_PATHS:
                req = f'GET {sock_path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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

                status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')

                if '200' in status_line or '404' not in status_line:
                    body = response.split(b'\r\n\r\n', 1)
                    if len(body) > 1:
                        body_text = body[1].decode('utf-8', errors='ignore')
                        if 'docker' in body_text.lower() or len(body_text) > 100:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port,
                                cvss_score=self.CVSS_SCORE, severity='critical',
                                description=f'Docker UNIX socket exposed via web root at {sock_path}',
                                solution=self.SOLUTION,
                                evidence=f'Docker socket accessible via HTTP on port {port} at {sock_path}',
                                references=[
                                    'https://www.tenable.com/plugins/nessus/109093',
                                ]
                            ))
                            writer.close()
                            await writer.wait_closed()
                            return

            writer.close()
            await writer.wait_closed()

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass
