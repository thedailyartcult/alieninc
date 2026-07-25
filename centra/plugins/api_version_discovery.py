"""
Plugin 1155: API Version Discovery & Deprecated Endpoint Detection
====================================================================
Discovers exposed API version endpoints and checks for deprecated versions.
"""
import asyncio
import re
import ssl

from plugins import NaslPlugin, PluginResult


class ApiVersionDiscovery(NaslPlugin):
    PLUGIN_ID = 1155
    NAME = 'API Version Discovery & Deprecated Endpoint Detection'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Discovers exposed API version endpoints (v1, v2, v3) and checks for '
        'deprecated/removed versions. Older API versions may lack security updates '
        'or contain known vulnerabilities. Versioned API paths can reveal the API '
        'evolution and potential weak points.'
    )
    SOLUTION = (
        'Remove deprecated API versions. Use proper API versioning with sunset '
        'headers. Ensure all active versions receive security updates.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    API_VERSION_PATHS = [
        '/api/v1', '/api/v2', '/api/v3', '/api/v4',
        '/v1', '/v2', '/v3', '/v4',
        '/api/v1/', '/api/v2/', '/api/v3/', '/api/v4/',
        '/api/v1.0', '/api/v2.0', '/api/v3.0',
        '/v1/', '/v2/', '/v3/',
        '/api/1', '/api/2', '/api/3',
        '/api/ver1', '/api/ver2', '/api/ver3',
        '/rest/v1', '/rest/v2', '/rest/v3',
        '/api/v1/users', '/api/v2/users', '/api/v3/users',
        '/api/v1/status', '/api/v2/status',
    ]

    SUNSET_HEADER = 'sunset'
    DEPRECATION_HEADERS = ['deprecation', 'deprecated', 'api-deprecated', 'x-api-deprecated']

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

                active_versions = []
                deprecated_versions = []
                legacy_info = []

                for path in self.API_VERSION_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nAccept: application/json\r\nConnection: close\r\n\r\n'
                        writer.write(req.encode())
                        await writer.drain()

                        response = b''
                        while True:
                            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                            if not chunk:
                                break
                            response += chunk
                            if len(response) > 32768:
                                break

                        writer.close()
                        await writer.wait_closed()

                        header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                        headers = {}
                        for line in header_section.split('\r\n')[1:]:
                            if ':' in line:
                                k, v = line.split(':', 1)
                                headers[k.strip().lower()] = v.strip()

                        status_line = header_section.split('\r\n')[0] if header_section else ''
                        status_code = 0
                        if status_line:
                            try:
                                status_code = int(status_line.split(' ')[1])
                            except (IndexError, ValueError):
                                pass

                        if status_code in (200, 201, 202, 301, 302, 307, 308):
                            body_section = response.split(b'\r\n\r\n', 1)
                            body_text = body_section[1].decode('utf-8', errors='ignore')[:2048] if len(body_section) > 1 else ''

                            version_match = re.search(r'v(\d+)', path, re.IGNORECASE)
                            version_num = version_match.group(1) if version_match else 'unknown'

                            version_entry = f'v{version_num} ({path}) [HTTP {status_code}]'

                            is_deprecated = False
                            sunset_info = None

                            if self.SUNSET_HEADER in headers:
                                is_deprecated = True
                                sunset_info = f'Sunset: {headers[self.SUNSET_HEADER]}'

                            for dep_header in self.DEPRECATION_HEADERS:
                                if dep_header in headers:
                                    is_deprecated = True
                                    if headers[dep_header].lower() in ('true', '1'):
                                        dep_info = f'Deprecated: {dep_header}={headers[dep_header]}'
                                        if sunset_info:
                                            sunset_info += ', ' + dep_info
                                        else:
                                            sunset_info = dep_info

                            if is_deprecated:
                                deprecated_versions.append(version_entry)
                                if sunset_info:
                                    legacy_info.append(f'{version_entry} - {sunset_info}')
                            else:
                                active_versions.append(version_entry)

                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                        pass

                if deprecated_versions:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='medium',
                        description=f'Deprecated API version(s) active: {len(deprecated_versions)} found. Active: {len(active_versions)}',
                        solution=self.SOLUTION,
                        evidence=f'Active: {", ".join(active_versions)} | Deprecated: {", ".join(deprecated_versions)}' if active_versions else f'Deprecated: {", ".join(deprecated_versions)}',
                        references=[
                            'https://www.rfc-editor.org/rfc/rfc8594',
                            'https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design',
                        ]
                    ))
                elif active_versions:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description=f'Active API version(s) found: {len(active_versions)}. No deprecated versions detected',
                        evidence=f'Active: {", ".join(active_versions)}'
                    ))
                else:
                    results.append(PluginResult(
                        vulnerable=False, target=target, port=port_to_check,
                        description='No versioned API endpoints detected'
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port_to_check,
                    description=f'Port {port_to_check} not reachable'
                ))

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No ports reachable for API version discovery'
            ))

        return results
