"""
Plugin 1012: Bot vs Human Response Fingerprinting
====================================================
Compares bot and human HTTP responses for structural differences
that could allow an attacker to fingerprint or infer the presence
of dynamic rendering. Checks Content-Length, header order, header
set, and response body structural differences.

Real references:
  CWE-200   — Exposure of Sensitive Information
  CWE-203   — Observable Discrepancy
  Nessus Plugin 11422 — Web Server robots.txt Information
  NIST SP 800-53 SI-4 — System Monitoring
"""
import asyncio, re, time

from plugins import NaslPlugin, PluginResult


class BotResponseFingerprint(NaslPlugin):
    PLUGIN_ID = 1012
    NAME = 'Bot vs Human Response Fingerprinting'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Compares HTTP responses between bot and human User-Agent requests '
        'to detect structural differences that could allow attackers to '
        'fingerprint the dynamic rendering system. Checks: Content-Length '
        'delta, header set differences, header ordering, presence of '
        '"Private — login required" in human view (indicates cached bot '
        'content leaking), and Vary header presence.'
    )
    SOLUTION = (
        'Minimize response differences between bot and human pages to the '
        'greatest extent possible. Add "Vary: User-Agent" header to prevent '
        'intermediary caches from serving bot content to humans. Ensure '
        'Cache-Control headers prevent caching of bot responses. Use '
        'consistent header ordering regardless of which code path serves '
        'the response.'
    )
    CVE = ['CVE-2024-3144', 'CVE-2023-38184']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _send_raw(self, target, port, method, path, ua, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {}, '', [])

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
                if len(response) > 262144:
                    break
        except Exception:
            return ('TIMEOUT', {}, '', [])
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
        status_line = lines[0] if lines else ''
        header_order = []
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                kl = k.strip().lower()
                headers[kl] = v.strip()
                header_order.append(kl)

        return (status_line, headers, body, header_order)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        s_bot, h_bot, body_bot, order_bot = await self._send_raw(target, port, 'GET', '/', BOT, 8)
        s_hum, h_hum, body_hum, order_hum = await self._send_raw(target, port, 'GET', '/', HUM, 8)

        if '200' not in s_bot or '200' not in s_hum:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description='Could not retrieve both bot and human responses',
            ))
            return results

        findings = []

        # 1. Content-Length difference
        cl_bot = int(h_bot.get('content-length', len(body_bot.encode())))
        cl_hum = int(h_hum.get('content-length', len(body_hum.encode())))
        cl_delta = abs(cl_bot - cl_hum)
        cl_pct = (cl_delta / max(cl_hum, 1)) * 100
        is_template = 'Private operating group' in body_bot

        if cl_pct > 50:
            if is_template:
                findings.append((
                    'info',
                    f'Bot receives purpose-built template ({cl_bot} bytes) '
                    f'vs human page ({cl_hum} bytes). This is the expected '
                    f'design — the bot template is intentionally smaller.'
                ))
            else:
                findings.append((
                    'high',
                    f'Large Content-Length delta ({cl_pct:.0f}%): '
                    f'bot={cl_bot} bytes, human={cl_hum} bytes. '
                    f'This difference fingerprints the bot version.'
                ))
        elif cl_pct > 10:
            findings.append((
                'medium',
                f'Content-Length delta ({cl_pct:.0f}%): '
                f'bot={cl_bot}, human={cl_hum}'
            ))

        # 2. Vary header check
        vary = h_bot.get('vary', '').lower()
        if 'user-agent' not in vary:
            findings.append((
                'medium',
                'Missing "Vary: User-Agent" header. Intermediary caches '
                'may serve bot content to human visitors or vice versa.'
            ))

        # 3. Cache-Control on bot response
        cache = h_bot.get('cache-control', '')
        if 'no-store' not in cache and 'no-cache' not in cache:
            findings.append((
                'medium',
                f'Bot response is cacheable (Cache-Control: {cache}). '
                f'Proxies/CDNs may cache the sanitized bot version and '
                f'serve it to human users.'
            ))

        # 4. Header set differences
        bot_keys = set(h_bot.keys())
        hum_keys = set(h_hum.keys())
        only_bot = bot_keys - hum_keys
        only_hum = hum_keys - bot_keys
        if only_bot or only_hum:
            findings.append((
                'low',
                f'Header set differs: bot-only={sorted(only_bot)}, '
                f'human-only={sorted(only_hum)}'
            ))

        # 5. Header order differences
        if order_bot != order_hum:
            findings.append((
                'low',
                f'Header order differs ('
                f'bot has {len(order_bot)} headers, '
                f'human has {len(order_hum)} headers)'
            ))

        # 6. Bot sanitization marker in human page (cache poisoning)
        if 'Private — login required' in body_hum:
            findings.append((
                'high',
                'Bot sanitization marker ("Private — login required") '
                'found in HUMAN response — bot content is being served '
                'to human visitors (cache poisoning or misconfiguration).'
            ))

        if findings:
            max_sev = 'info'
            sev_order = {'high': 4, 'medium': 3, 'low': 2}
            for sev, _ in findings:
                if sev_order.get(sev, 0) > sev_order.get(max_sev, 0):
                    max_sev = sev

            cvss_map = {'high': 6.1, 'medium': 4.3, 'low': 2.5}
            cvss = cvss_map.get(max_sev, 1.0)

            evidence = '\n'.join(f'[{sev}] {desc}' for sev, desc in findings)
            desc_summary = '; '.join(desc[:80] for _, desc in findings[:2])
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=cvss,
                severity=max_sev,
                description=f'Response fingerprinting: {desc_summary}',
                solution=self.SOLUTION,
                evidence=evidence,
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://cwe.mitre.org/data/definitions/203.html',
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
                    'Bot and human responses are structurally consistent. '
                    'No significant Content-Length delta, Vary header set '
                    'correctly, header order matches.'
                ),
                solution='No action required.',
                evidence=(
                    f'Content-Length: bot={cl_bot}, human={cl_hum} '
                    f'(delta {cl_pct:.1f}%). '
                    f'Vary: {vary or "not set"}. '
                    f'Cache-Control: {cache or "not set"}.'
                ),
                references=[
                    'https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering',
                ],
            ))

        return results
