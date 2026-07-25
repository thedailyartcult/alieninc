"""
Plugin 1148: HTTP Caching Policy Audit
========================================
Audits HTTP Cache-Control headers for security-sensitive content.
"""
import asyncio
import ssl

from plugins import NaslPlugin, PluginResult


class CachingHeaders(NaslPlugin):
    PLUGIN_ID = 1148
    NAME = 'HTTP Caching Policy Audit'
    FAMILY = 'Web Applications'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Audits HTTP Cache-Control headers for security-sensitive content. Missing '
        'or permissive caching headers can cause sensitive data to be stored in '
        'browser caches, proxy caches, or CDN caches, making it accessible to '
        'other users or attackers with local access.'
    )
    SOLUTION = (
        'Set Cache-Control: no-store for sensitive pages. Use private for '
        'user-specific content. Set appropriate max-age values.'
    )
    CVE = []
    PORTS = [80, 443, 8080, 8443]

    SENSITIVE_PATHS = [
        '/', '/login', '/admin', '/dashboard', '/account',
        '/api/users', '/api/v1/users', '/profile', '/settings',
        '/api/session', '/api/token', '/api/auth',
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

                for path in self.SENSITIVE_PATHS:
                    try:
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(target, port_to_check, ssl=ctx),
                            timeout=5
                        )

                        req = f'GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: Centra/1.0\r\nConnection: close\r\n\r\n'
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
                                k, v = line.split(':', 1)
                                headers[k.strip().lower()] = v.strip()

                        cache_control = headers.get('cache-control', '')
                        pragma = headers.get('pragma', '')

                        issues = []
                        if not cache_control:
                            issues.append('No Cache-Control header set')
                        else:
                            cc_lower = cache_control.lower()
                            if 'no-store' not in cc_lower:
                                issues.append('Missing no-store directive')
                            if 'no-cache' not in cc_lower and 'no-store' not in cc_lower:
                                issues.append('Missing no-cache directive')
                            if 'private' not in cc_lower and 'no-store' not in cc_lower:
                                if 'public' in cc_lower or not any(x in cc_lower for x in ('private', 'no-store')):
                                    issues.append('Publicly cacheable (missing private directive)')

                            if 'max-age=' in cc_lower:
                                try:
                                    max_age_str = cc_lower.split('max-age=')[1].split(',')[0].strip()
                                    max_age = int(max_age_str)
                                    if max_age > 86400:
                                        issues.append(f'Excessive max-age: {max_age}s (>{86400}s)')
                                except (ValueError, IndexError):
                                    pass

                        if pragma and pragma.lower() != 'no-cache':
                            if 'no-cache' not in cache_control.lower():
                                issues.append('Pragma header set to: ' + pragma)

                        if issues:
                            results.append(PluginResult(
                                vulnerable=True, target=target, port=port_to_check,
                                cvss_score=self.CVSS_SCORE, severity='medium',
                                description=f'Insecure caching policy for {path}: {len(issues)} issue(s)',
                                solution=self.SOLUTION,
                                evidence=f'Path: {path}, Cache-Control: {cache_control or "(not set)"}, Issues: {" | ".join(issues)}',
                                references=[
                                    'https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html',
                                    'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control',
                                ]
                            ))

                    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                        pass

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError):
                pass

        if not results:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port or 0,
                description='No insecure caching policies detected on checked paths'
            ))

        return results
