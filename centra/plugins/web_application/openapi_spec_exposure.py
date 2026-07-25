"""
Plugin 1147: OpenAPI/Swagger Spec Exposure Detection
======================================================
Detects exposed OpenAPI/Swagger specification files.
"""
import asyncio
import json
import ssl
import re

from plugins import NaslPlugin, PluginResult


class OpenapiSpecExposure(NaslPlugin):
    PLUGIN_ID = 1147
    NAME = 'OpenAPI/Swagger Spec Exposure Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Detects exposed OpenAPI/Swagger specification files (openapi.json, '
        'swagger.json, api-docs, /v3/api-docs) that reveal the full API surface '
        'including endpoints, parameters, authentication methods, and data schemas.'
    )
    SOLUTION = (
        'Disable API documentation in production. Use authentication for API docs. '
        'Serve docs only from internal networks.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SPEC_PATHS = [
        '/openapi.json',
        '/swagger.json',
        '/api-docs',
        '/v3/api-docs',
        '/v2/api-docs',
        '/swagger/v1/swagger.json',
        '/api/swagger.json',
        '/api/v1/openapi.json',
        '/api/v2/openapi.json',
        '/api/v3/openapi.json',
        '/docs/swagger.json',
        '/swagger-ui/swagger.json',
        '/openapi.yaml',
        '/swagger.yaml',
        '/api/swagger.yaml',
        '/docs',
        '/swagger-ui.html',
        '/api/docs',
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

                for path in self.SPEC_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )

                        host_header = target
                        if target in ('127.0.0.1', 'localhost', '::1'):
                            host_header = 'alieninc.tech'

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()

                        response = b''
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 65536:
                                break

                        writer.close()
                        await writer.wait_closed()

                        header_section, _, body = response.partition(b'\r\n\r\n')
                        status_line = header_section.decode('utf-8', errors='ignore').split('\r\n')[0] if header_section else ''
                        status_code = 0
                        if status_line:
                            try:
                                status_code = int(status_line.split(' ')[1])
                            except (IndexError, ValueError):
                                pass

                        if status_code not in (200, 200) or not body:
                            continue

                        body_text = body.decode('utf-8', errors='ignore')[:8192]

                        if self._is_openapi_spec(body_text):
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'OpenAPI/Swagger specification exposed at {path}',
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, response: {status_code}',
                                references=[
                                    'https://www.openapis.org/',
                                    'https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html',
                                ]
                            ))
                            break

                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                        pass

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No OpenAPI/Swagger specification found on checked ports'
            ))

        return results

    def _is_openapi_spec(self, body: str) -> bool:
        if re.search(r'"openapi"\s*:\s*"[23]\.', body):
            return True
        if re.search(r'"swagger"\s*:\s*"[23]\.', body):
            return True
        if re.search(r'"info"\s*:\s*\{', body) and re.search(r'"paths"\s*:\s*\{', body):
            return True
        if re.search(r'openapi:\s*[23]\.', body, re.IGNORECASE):
            return True
        if re.search(r'swagger:\s*[23]\.', body, re.IGNORECASE):
            return True
        if re.search(r'"swaggerVersion"\s*:', body):
            return True
        try:
            parsed = json.loads(body)
            if 'openapi' in parsed or 'swagger' in parsed:
                return True
        except (json.JSONDecodeError, ValueError):
            pass
        return False
