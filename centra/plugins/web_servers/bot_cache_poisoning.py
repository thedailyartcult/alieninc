"""
Plugin 1018: Cache Poisoning via Bot User-Agent
=================================================
Tests whether bot (sanitized) responses can be cached by intermediary
proxies or CDNs and subsequently served to human visitors. If bot
responses lack proper Cache-Control: no-store headers, and the
Vary header does not include User-Agent, upstream caches may store
the sanitized version and poison the cache for all users.

Real references:
  CWE-524   — Use of Cache Containing Sensitive Information
  CWE-525   — Use of Web Browser Cache Containing Sensitive Information
  OWASP-2017-A6 — Security Misconfiguration
  Nessus Plugin 85582 — Web Cache Deception
"""
import asyncio, re

from plugins import NaslPlugin, PluginResult


class BotCachePoisoning(NaslPlugin):
    PLUGIN_ID = 1018
    NAME = 'Cache Poisoning via Bot User-Agent'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 6.1
    DESCRIPTION = (
        'Tests whether the bot-sanitized response could be cached by '
        'intermediary proxies/CDNs and served to human users. Checks '
        'Cache-Control directives, Vary header presence, Age header, '
        'ETag/Last-Modified consistency between bot and human responses, '
        'and whether the sanitized bot response contains cache-friendly '
        'headers that would allow it to be stored and re-served.'
    )
    SOLUTION = (
        '1. Add "Cache-Control: no-store, no-cache, must-revalidate" to '
        'all bot responses. '
        '2. Add "Vary: User-Agent" to inform caches that content varies '
        'by UA. '
        '3. Use different ETags for bot and human versions. '
        '4. Set "Expires: 0" or use past-dated Expires headers for bot '
        'responses. '
        '5. If using a CDN, configure rules to bypass cache for known '
        'bot User-Agent strings.'
    )
    CVE = ['CVE-2024-27919', 'CVE-2023-44487']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _send_raw(self, target, port, method, path, ua, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {})

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
                if len(response) > 32768:
                    break
        except Exception:
            return ('TIMEOUT', {})
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        header_section = response.split(b'\r\n\r\n', 1)[0].decode('utf-8', errors='ignore')
        lines = header_section.split('\r\n')
        status_line = lines[0] if lines else ''
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        return (status_line, headers)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        s_bot, h_bot = await self._send_raw(target, port, 'GET', '/', BOT, 8)
        s_hum, h_hum = await self._send_raw(target, port, 'GET', '/', HUM, 8)

        if '200' not in s_bot:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Bot response not available: {s_bot[:50]}',
            ))
            return results

        findings = []

        # 1. Cache-Control check
        cc = h_bot.get('cache-control', '').lower()
        is_uncacheable = any(d in cc for d in [
            'no-store', 'no-cache', 'must-revalidate', 'private'
        ])
        if not cc:
            findings.append((
                'high',
                'No Cache-Control header on bot response. Proxies and '
                'browsers will cache the sanitized bot version using '
                'heuristic defaults. Cache poisoning risk is HIGH.'
            ))
        elif not is_uncacheable:
            findings.append((
                'medium',
                f'Cache-Control allows caching: "{cc}". Bot responses '
                f'may be stored by intermediary caches.'
            ))

        # 2. Vary check
        vary = h_bot.get('vary', '').lower()
        if 'user-agent' not in vary:
            findings.append((
                'high',
                'Vary header does not include "User-Agent". Caches will '
                'not differentiate bot and human responses. A cache may '
                'serve the sanitized bot version to all users regardless '
                'of their User-Agent.'
            ))

        # 3. ETag/Last-Modified check
        etag_bot = h_bot.get('etag', '')
        etag_hum = h_hum.get('etag', '') if '200' in s_hum else ''
        if etag_bot and etag_hum and etag_bot == etag_hum:
            findings.append((
                'medium',
                f'Same ETag for bot and human responses ({etag_bot[:30]}). '
                f'Caches treat them as identical resources.'
            ))

        # 4. Expires/Pragma check
        expires = h_bot.get('expires', '')
        pragma = h_bot.get('pragma', '').lower()
        if expires and 'no-cache' not in pragma:
            findings.append((
                'low',
                f'Expires header set on bot response: {expires}. '
                f'May allow caching until expiration.'
            ))

        # 5. Age header check
        if 'age' in h_bot:
            findings.append((
                'info',
                f'Age header present: {h_bot["age"]}s. Response already '
                f'served from cache — verify correct UA was cached.'
            ))

        if findings:
            max_sev = 'info'
            sev_order = {'high': 4, 'medium': 3, 'low': 2, 'info': 1}
            for sev, _ in findings:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev

            cvss_map = {'high': 6.1, 'medium': 4.3, 'low': 2.5}
            cvss = cvss_map.get(max_sev, 1.0)

            evidence = '\n'.join(f'[{sev}] {desc}' for sev, desc in findings)
            desc_summary = '; '.join(d[:80] for _, d in findings[:2])
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description=f'Cache poisoning risk: {desc_summary}',
                solution=self.SOLUTION,
                evidence=evidence,
                references=[
                    'https://cwe.mitre.org/data/definitions/524.html',
                    'https://cwe.mitre.org/data/definitions/525.html',
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
                    'Bot responses properly marked as uncacheable. '
                    'Cache-Control, Vary, and ETag headers correctly '
                    'prevent cache poisoning.'
                ),
                solution='No action required.',
                evidence=(
                    f'Cache-Control: {cc or "not set"}. '
                    f'Vary: {vary or "not set"}. '
                    f'ETag identical: {etag_bot == etag_hum if etag_bot else "N/A"}.'
                ),
                references=[
                    'https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering',
                ],
            ))

        return results
