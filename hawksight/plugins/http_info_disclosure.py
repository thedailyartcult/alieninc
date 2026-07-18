"""
Plugin 1009: HTTP Information Disclosure
==========================================
Detects information leakage via HTTP headers and error pages.
Real CVEs: CVE-2023-46604, CVE-2022-1388 (F5 BIG-IP)
"""
import asyncio

from plugins import NaslPlugin, PluginResult


class HttpInfoDisclosure(NaslPlugin):
    PLUGIN_ID = 1009
    NAME = 'HTTP Information Disclosure'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'The web server discloses sensitive information through HTTP headers, '
        'error pages, or default content. This information can assist attackers '
        'in fingerprinting the server and identifying known vulnerabilities.'
    )
    SOLUTION = (
        'Remove or customize server banner headers. Configure custom error pages. '
        'Disable directory listing. Remove default application pages and '
        'server-status endpoints.'
    )
    CVE = ['CVE-2023-46604', 'CVE-2022-1388']
    PORTS = [80, 443]

    async def check_target(self, target: str, port: int | None = 80) -> list[PluginResult]:
        port = port or 80
        results = []

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=5
            )

            req = f'GET / HTTP/1.1\r\nHost: {target}\r\nUser-Agent: Hawksight/1.0\r\nConnection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()

            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                if not chunk:
                    break
                response += chunk
                if len(response) > 16384:
                    break

            writer.close()
            await writer.wait_closed()

            header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
            headers = {}
            for line in header_section.split('\r\n')[1:]:
                if ':' in line:
                    key, val = line.split(':', 1)
                    headers[key.strip().lower()] = val.strip()

            disclosures = []

            server_val = headers.get('server', '')
            if server_val and any(v in server_val.lower() for v in ['apache/', 'nginx/', 'iis/', 'tomcat']):
                disclosures.append(f'Server header reveals software: {server_val}')

            x_powered = headers.get('x-powered-by', '')
            if x_powered:
                disclosures.append(f'X-Powered-By reveals stack: {x_powered}')

            if 'x-aspnet-version' in headers:
                disclosures.append(f'ASP.NET version exposed: {headers["x-aspnet-version"]}')

            if 'x-aspnetmvc-version' in headers:
                disclosures.append(f'ASP.NET MVC version exposed: {headers["x-aspnetmvc-version"]}')

            if 'x-debug' in headers or 'x-debug-token' in headers:
                disclosures.append('Debug information headers detected')

            if 'www-authenticate' in headers:
                auth_header = headers['www-authenticate']
                if 'basic' in auth_header.lower():
                    disclosures.append('Basic authentication scheme detected')

            body = response.split(b'\r\n\r\n')[1:].decode('utf-8', errors='ignore')[:2000]
            error_patterns = [
                'stack trace', 'traceback', 'exception in', 'syntax error',
                'uncaught exception', 'debug mode', 'development server',
            ]
            for pattern in error_patterns:
                if pattern.lower() in body.lower():
                    disclosures.append(f'Error/debug information in response body: "{pattern}"')
                    break

            if disclosures:
                results.append(PluginResult(
                    vulnerable=True,
                    target=target,
                    port=port,
                    cvss_score=self.CVSS_SCORE,
                    severity='medium',
                    description=f'Information disclosure detected: {"; ".join(disclosures)}',
                    solution=self.SOLUTION,
                    evidence=f'Headers: {dict(list(headers.items())[:8])}',
                    references=[
                        'https://nvd.nist.gov/vuln/detail/CVE-2023-46604',
                        'https://www.owasp.org/index.php/Information_Leakage',
                    ]
                ))
            else:
                results.append(PluginResult(
                    vulnerable=False, target=target, port=port,
                    description='No information disclosure detected'
                ))

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'HTTP port {port} not reachable'
            ))

        return results
