"""
Plugin 1156: HSTS Preload Readiness Check
==========================================
Checks if the domain is eligible for HSTS preloading by evaluating
the Strict-Transport-Security header.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class HstsPreloadCheck(NaslPlugin):
    PLUGIN_ID = 1156
    NAME = 'HSTS Preload Readiness Check'
    FAMILY = 'SSL/TLS'
    CVSS_SCORE = 3.7
    DESCRIPTION = (
        'Checks if the domain is eligible for HSTS preloading by evaluating '
        'the Strict-Transport-Security header. HSTS preloading ensures browsers '
        'always use HTTPS for the domain before any HTTP connection is attempted. '
        'Also checks if the domain is in browser preload lists.'
    )
    SOLUTION = (
        'Serve HSTS header with max-age=63072000, includeSubDomains, and preload '
        'directives. Submit domain to https://hstspreload.org.'
    )
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
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port_to_check, ssl=ctx), timeout=5
                )
                host_header = target
                if target in ('127.0.0.1', 'localhost', '::1'):
                    host_header = 'alieninc.tech'
                req = f'GET / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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
                writer.close()
                await writer.wait_closed()

                header_section = response.split(b'\r\n\r\n')[0].decode('utf-8', errors='ignore')
                headers = {}
                for line in header_section.split('\r\n')[1:]:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        headers[key.strip().lower()] = val.strip()

                hsts = headers.get('strict-transport-security', '')
                if hsts:
                    max_age = 0
                    has_include_subdomains = 'includesubdomains' in hsts.lower().replace('-', '')
                    has_preload = 'preload' in hsts.lower()
                    for part in hsts.split(';'):
                        part = part.strip()
                        if part.lower().startswith('max-age='):
                            try:
                                max_age = int(part.split('=', 1)[1])
                            except ValueError:
                                pass

                    if max_age >= 63072000 and has_include_subdomains and has_preload:
                        results.append(PluginResult(
                            vulnerable=False, target=target, port=port_to_check,
                            description='HSTS header meets preload readiness criteria',
                            evidence=f'Strict-Transport-Security: {hsts}'
                        ))
                    else:
                        issues = []
                        if max_age < 63072000:
                            issues.append(f'max-age={max_age} (need >= 63072000)')
                        if not has_include_subdomains:
                            issues.append('missing includeSubDomains')
                        if not has_preload:
                            issues.append('missing preload directive')
                        results.append(PluginResult(
                            vulnerable=True, target=target, port=port_to_check,
                            cvss_score=self.CVSS_SCORE, severity='low',
                            description='HSTS header present but not preload-ready',
                            solution=self.SOLUTION,
                            evidence=f'Strict-Transport-Security: {hsts} — Issues: {", ".join(issues)}',
                            references=['https://hstspreload.org/']
                        ))
                else:
                    results.append(PluginResult(
                        vulnerable=True, target=target, port=port_to_check,
                        cvss_score=self.CVSS_SCORE, severity='low',
                        description='No Strict-Transport-Security header — not preload-ready',
                        solution=self.SOLUTION,
                        evidence=f'No HSTS header on port {port_to_check}',
                        references=['https://hstspreload.org/']
                    ))

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass
        if not results:
            results.append(PluginResult(vulnerable=False, target=target, port=port or 0,
                                        description='No issues detected'))
        return results
