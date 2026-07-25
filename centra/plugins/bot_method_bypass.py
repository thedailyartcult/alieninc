"""
Plugin 1011: Bot Detection Bypass via HTTP Methods
====================================================
Tests whether bot detection can be evaded by using HTTP methods
other than GET. Many WAFs and dynamic rendering proxies only inspect
GET requests — HEAD, POST, OPTIONS, or PUT may return unsanitized
content to bots.

Real references:
  CWE-200   — Exposure of Sensitive Information to an Unauthorized Actor
  CWE-306   — Missing Authentication for Critical Function
  OWASP-ASVS V4.0.3-4.1.1 — Verify enforcement of access controls
  Nessus Plugin 17656 — HTTP Methods Allowed (per directory)
"""
import asyncio, re, time

from plugins import NaslPlugin, PluginResult


BOT_TEMPLATE_MARKER = 'Private operating group'


class BotMethodBypass(NaslPlugin):
    PLUGIN_ID = 1011
    NAME = 'Bot Detection Bypass via HTTP Methods'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Tests whether the bot detection / dynamic rendering can be '
        'circumvented by using non-GET HTTP methods (HEAD, POST, OPTIONS, '
        'PUT). If an attacker sends a Googlebot User-Agent with a HEAD '
        'request and receives unsanitized headers or content, they can '
        'fingerprint the human version without triggering bot blocks.'
    )
    SOLUTION = (
        'Ensure bot detection is applied uniformly across all HTTP methods '
        'that return content. Block or sanitize responses for known bot '
        'User-Agents regardless of request method. Return 405 for methods '
        'not explicitly supported.'
    )
    CVE = ['CVE-2023-46805', 'CVE-2024-27198']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _send_raw(self, target, port, method, path, ua, timeout=8):
        """Send an arbitrary HTTP request, return (status_line, headers, body)."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {}, '')

        try:
            req = (
                f'{method} {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
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
        header_section = parts[0].decode('utf-8', errors='ignore') if parts else ''
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''

        lines = header_section.split('\r\n')
        status_line = lines[0] if lines else ''

        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        return (status_line, headers, body)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT_UA = 'Googlebot/2.1 (+http://www.google.com/bot.html)'
        HUMAN_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        # Baseline: GET with human UA
        status, hdrs, body_get_human = await self._send_raw(
            target, port, 'GET', '/', HUMAN_UA, 8
        )
        if '200' not in status:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Target unreachable via GET: {status[:50]}',
            ))
            return results

        sanitized_marker = BOT_TEMPLATE_MARKER
        has_data_scripts = 'ecosystem-data.js' in body_get_human

        # Test each HTTP method with bot UA
        methods = ['GET', 'HEAD', 'POST', 'OPTIONS', 'PUT']
        bypasses = []
        method_details = {}

        for method in methods:
            t0 = time.monotonic()
            status, hdrs, body = await self._send_raw(
                target, port, method, '/', BOT_UA, 8
            )
            elapsed = time.monotonic() - t0

            content_length = hdrs.get('content-length', 'unknown')
            is_sanitized = sanitized_marker in body
            has_scripts = 'ecosystem-data.js' in body if body else False
            is_200 = '200' in status

            method_details[method] = {
                'status': status[:50],
                'len': content_length,
                'sanitized': is_sanitized,
                'scripts': has_scripts,
                'time': f'{elapsed:.3f}s',
            }

            if is_200 and not is_sanitized:
                # For HEAD/OPTIONS, body is empty — compare Content-Length instead
                if method in ('HEAD', 'OPTIONS'):
                    cl_sanitized = hdrs.get('content-length', '0')
                    sanitized_markers = [
                        'no-store',
                        'AlienInc',
                    ]
                    has_sanitized_headers = any(
                        m in str(hdrs.get('cache-control', '')).lower()
                        for m in sanitized_markers
                    )
                    # HEAD returns 0 body — this is expected. Check if headers
                    # suggest bot detection was applied (Cache-Control set, etc.)
                    if 'content-length' in hdrs and has_sanitized_headers:
                        continue  # HEAD is properly handled, skip flagging
                    bypasses.append(
                        f'{method}: HTTP 200 with {cl_sanitized}-byte Content-Length'
                    )
                elif method == 'GET':
                    bypasses.append(f'{method}: unsanitized GET (bot detection failure)')
                else:
                    bypasses.append(
                        f'{method}: HTTP 200 unsanitized (content-length={content_length})'
                    )

        if bypasses:
            evidence = '\n'.join(
                f'{method}: status={d["status"]} len={d["len"]} '
                f'sanitized={d["sanitized"]} time={d["time"]}'
                for method, d in method_details.items()
            )
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=(
                    f'Bot detection bypass via HTTP method — '
                    f'{len(bypasses)} method(s) evade sanitization: '
                    f'{"; ".join(bypasses)}'
                ),
                solution=self.SOLUTION,
                evidence=evidence,
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://cwe.mitre.org/data/definitions/306.html',
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))
        else:
            evidence = '\n'.join(
                f'{method}: sanitized={d["sanitized"]} time={d["time"]}'
                for method, d in method_details.items()
            )
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description=(
                    f'Bot detection consistent across {len(methods)} HTTP '
                    f'methods — no bypass via HEAD/POST/OPTIONS/PUT.'
                ),
                solution='No action required.',
                evidence=evidence,
                references=[
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))

        return results
