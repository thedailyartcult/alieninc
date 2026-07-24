"""
Plugin 1014: Error Page Information Disclosure to Bots
========================================================
Tests whether error pages (404, 500, 403) leak server technology,
version information, stack traces, or internal paths to bot
User-Agents. Default web server error pages often disclose the
server software and version, aiding targeted attacks.

Real references:
  CWE-200   — Exposure of Sensitive Information
  OWASP-ASVS V4.0.3-7.4.1 — Error handling does not disclose sensitive info
  Nessus Plugin 10151 — Web Server HTTP Header Information Disclosure
  Nessus Plugin 48204 — Apache Tomcat Default Error Page Information Disclosure
"""
import asyncio, re, ssl

from plugins import NaslPlugin, PluginResult


class BotErrorDisclosure(NaslPlugin):
    PLUGIN_ID = 1014
    NAME = 'Error Page Information Disclosure to Bots'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.0
    DESCRIPTION = (
        'Probes non-existent paths and malformed requests with bot '
        'User-Agent strings to check whether error responses leak server '
        'version, framework information, internal paths, or stack traces. '
        'Default server error pages often reveal the technology stack.'
    )
    SOLUTION = (
        'Configure custom error pages for all HTTP status codes (404, 403, '
        '500, 502, 503). Ensure error pages do not disclose server version, '
        'framework name, or internal paths. Remove X-Powered-By and Server '
        'headers or genericize them.'
    )
    CVE = ['CVE-2021-42013']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    DISCLOSURE_PATTERNS = [
        (r'(?:Apache|nginx|IIS|Tomcat|Jetty|Gunicorn|uWSGI|Werkzeug|'
         r'CherryPy|Tornado|Lighttpd|Caddy|Traefik|HAProxy)', 'server name'),
        (r'(?:PHP|Python|Ruby|Node\.js|Java|\.NET|ASP\.NET|Perl|Go)'
         r'\s*\d+\.\d+', 'runtime version'),
        (r'Traceback\s*\(most recent call last\)', 'stack trace'),
        (r'(?:File\s+"[^"]+",\s*line\s*\d+|at\s+\S+\.\S+:\d+:\d+)',
         'source file reference'),
        (r'(?:Exception|Error|Warning|Fatal|Notice)(?:\s*:)', 'error type'),
        (r'(?:DEBUG\s*[=:]\s*True|SQLSTATE|ORA-\d+|MySQL\s*Error|'
         r'SQLite3::|psycopg2\.)', 'database error'),
        (r'(?:X-Powered-By|X-Generator|X-AspNet-Version|X-Runtime)',
         'technology header'),
        (r'(?:/var/www|/usr/share|/home/\w+|C:\\inetpub|'
         r'C:\\xampp|/opt/tomcat)', 'internal path'),
    ]

    async def _send_raw(self, target, port, method, path, ua, timeout=8):
        try:
            host_header = target
            if target in ('127.0.0.1', 'localhost', '::1'):
                host_header = 'alieninc.tech'
            if port == 443:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port, ssl=ssl_ctx), timeout=timeout
                )
            else:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=timeout
                )
        except Exception:
            return ('ERROR', {}, '')

        try:
            req = (
                f'{method} {path} HTTP/1.1\r\n'
                f'Host: {host_header}\r\n'
                f'User-Agent: {ua}\r\n'
                f'Connection: close\r\n'
                f'\r\n'
            )
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                if not chunk:
                    break
                response += chunk
                if len(response) > 131072:
                    break
        except Exception:
            return ('TIMEOUT', {}, '')
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        parts = response.split(b'\r\n\r\n', 1)
        header_section = parts[0].decode('utf-8', errors='ignore')
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        lines = header_section.split('\r\n')
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        status_line = lines[0] if lines else ''
        return (status_line, headers, body)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        # Probe multiple non-existent paths
        probe_paths = [
            '/nonexistent-page-404-test',
            '/.env',
            '/wp-admin/',
            '/api/v2/',
            '/%00/index.html',
            '/<script>alert(1)</script>',
        ]

        all_disclosures = []

        for path in probe_paths:
            for label, ua in [('bot', BOT), ('human', HUM)]:
                status, headers, body = await self._send_raw(
                    target, port, 'GET', path, ua, 8
                )
                if 'ERROR' in status or 'TIMEOUT' in status:
                    continue

                # Check response headers for technology disclosure
                # Skip checks for 400 responses (nginx early rejection for malformed requests)
                if '400' in status:
                    await asyncio.sleep(0.05)
                    continue
                server_val = headers.get('server', '')
                # Only flag real technology servers, not custom/anonymized names
                real_servers = r'(?:Apache|nginx|IIS|Tomcat|Jetty|Gunicorn|uWSGI|' \
                               r'Werkzeug|CherryPy|Tornado|Lighttpd|Caddy|Traefik|HAProxy|' \
                               r'PHP|openresty|Node\.js|Express|Flask|Django|Rails)'
                if re.search(real_servers, server_val, re.IGNORECASE):
                    all_disclosures.append(
                        f'{label} {path} → header server: {server_val}'
                    )
                for hdr in ['x-powered-by', 'x-generator',
                            'x-aspnet-version', 'x-runtime']:
                    if hdr in headers:
                        all_disclosures.append(
                            f'{label} {path} → header {hdr}: {headers[hdr]}'
                        )

                # Check body for disclosure patterns
                for pattern, name in self.DISCLOSURE_PATTERNS:
                    matches = re.findall(pattern, body, re.IGNORECASE)
                    for m in set(matches):
                        all_disclosures.append(
                            f'{label} {path} → {name}: "{m[:80]}"'
                        )

                await asyncio.sleep(0.05)

        if all_disclosures:
            unique = list(dict.fromkeys(all_disclosures))  # dedupe preserve order
            max_sev = 'medium'
            if any('stack trace' in d for d in unique):
                max_sev = 'high'
            elif any('server name' in d for d in unique):
                max_sev = 'medium'

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=5.0 if max_sev == 'high' else 3.1,
                severity=max_sev,
                description=(
                    f'Error pages leak information — {len(unique)} '
                    f'disclosure(s) found in bot/human error responses.'
                ),
                solution=self.SOLUTION,
                evidence='\n'.join(unique[:10]),
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description=(
                    'Error pages are clean — no server version, stack trace, '
                    'or technology disclosure detected in error responses.'
                ),
                solution='No action required.',
                evidence=f'Probed {len(probe_paths)} paths with bot and human UAs — no info disclosure.',
                references=[
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))

        return results
