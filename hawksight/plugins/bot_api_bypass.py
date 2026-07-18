"""
Plugin 1023: API Endpoint Bot Bypass
======================================
Tests whether API endpoints (specifically /api/competitors and
/api/prices) apply bot detection. Currently these endpoints
return full financial data (competitor market caps, revenues,
live stock prices) to any User-Agent, including bots. This is
a direct data leak that bypasses all HTML sanitization.

Real references:
  CWE-200   — Exposure of Sensitive Information
  CWE-306   — Missing Authentication for Critical Function
  OWASP API4:2023 — Unrestricted Resource Consumption
"""
import asyncio, json, re

from plugins import NaslPlugin, PluginResult


class ApiEndpointBotBypass(NaslPlugin):
    PLUGIN_ID = 1023
    NAME = 'API Endpoint Bot Bypass'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 7.5
    DESCRIPTION = (
        'Tests whether the /api/competitors and /api/prices endpoints '
        'return real financial data to bot User-Agent strings. If these '
        'API endpoints bypass bot detection, attackers can directly query '
        'them for competitor market caps, revenues, P/E ratios, live stock '
        'prices, and company operating data without any HTML sanitization.'
    )
    SOLUTION = (
        '1. Apply bot detection to /api/* routes. Return empty or sanitized '
        'JSON ({}, [], or {"error":"forbidden"}) for known bot UAs. '
        '2. Require authentication for sensitive API endpoints. '
        '3. Implement rate limiting to prevent data harvesting. '
        '4. Add CORS restrictions so the API is only accessible from the '
        'same origin.'
    )
    CVE = ['CVE-2021-42013']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    API_ENDPOINTS = [
        ('/api/competitors', 'competitor financial data'),
        ('/api/prices', 'live stock prices'),
    ]

    SENSITIVE_FIELDS = [
        'marketCap', 'revenue', 'netIncome', 'ebitda', 'pe',
        'price', 'priceChange', 'priceChangePct', 'name',
    ]

    async def _send_raw(self, target, port, path, ua, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', {})

        try:
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: {ua}\r\n'
                f'Connection: close\r\n\r\n'
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
            return ('TIMEOUT', {})
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
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        return (status_line, headers, body)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        BOT = 'Googlebot/2.1'
        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        bot_leaks = []
        evidence_lines = []

        for endpoint, description in self.API_ENDPOINTS:
            for ua_label, ua in [('bot', BOT), ('human', HUM)]:
                s, h, body = await self._send_raw(target, port, endpoint, ua, 10)
                await asyncio.sleep(0.1)

                is_200 = '200' in s
                body_len = len(body) if body else 0
                content_type = h.get('content-type', 'unknown')

                evidence_lines.append(
                    f'{ua_label} {endpoint}: {s[:40]} len={body_len} type={content_type}'
                )

                if not is_200 or body_len < 10:
                    continue

                # Try to parse as JSON and check for sensitive data
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    continue

                # Check for sensitive financial fields
                sensitive_found = []
                if isinstance(data, dict):
                    for key in data.keys():
                        if any(sf.lower() in key.lower() for sf in self.SENSITIVE_FIELDS):
                            sensitive_found.append(key)
                    # Check nested
                    if 'competitors' in data and isinstance(data['competitors'], list):
                        comp = data['competitors']
                        if comp and isinstance(comp[0], dict):
                            sample_keys = list(comp[0].keys())[:5]
                            sensitive_found.extend(
                                k for k in sample_keys
                                if any(sf.lower() in k.lower() for sf in self.SENSITIVE_FIELDS)
                            )

                if sensitive_found and ua_label == 'bot':
                    bot_leaks.append({
                        'endpoint': endpoint,
                        'description': description,
                        'fields': list(set(sensitive_found))[:5],
                        'body_len': body_len,
                    })

        if bot_leaks:
            for leak in bot_leaks:
                evidence_lines.append(
                    f'LEAK: {leak["endpoint"]} returns '
                    f'{", ".join(leak["fields"])} ({leak["body_len"]}B) to bot UA'
                )

            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=(
                    f'API endpoint bot bypass — {len(bot_leaks)} endpoint(s) '
                    f'return real financial data to bot User-Agent: '
                    f'{"; ".join(l["endpoint"] for l in bot_leaks)}. '
                    f'Bots can query these directly without any HTML '
                    f'sanitization or bot detection.'
                ),
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://cwe.mitre.org/data/definitions/306.html',
                ],
            ))
        else:
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description='API endpoints apply bot detection. No financial data returned to bot UAs.',
                solution='No action required.',
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://owasp.org/www-project-api-security/',
                ],
            ))

        return results
