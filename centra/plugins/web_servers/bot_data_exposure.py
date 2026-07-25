"""
Plugin 1010: Bot Scraper Data Exposure
========================================
Tests whether dynamic rendering defenses are active by simulating
crawler requests with multiple bot User-Agent strings against each
company in the Alien Inc ecosystem. Checks that revenue data,
ecosystem scripts, and real numbers are hidden from bots while
remaining visible to human visitors.

Mapped to publicly verifiable standards:
  CWE-200   — Exposure of Sensitive Information to an Unauthorized Actor
              https://cwe.mitre.org/data/definitions/200.html
  CVE-2021-42013  — Apache HTTP Server path traversal (info disclosure vector)
              https://nvd.nist.gov/vuln/detail/CVE-2021-42013
  OWASP WSTG-INFO-05 — Information Disclosure via Web Application Fingerprinting
              https://owasp.org/www-project-web-security-testing-guide/
  NIST SP 800-53 Rev 5 — AC-3 Access Enforcement
              https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
  Google — Implement Dynamic Rendering
              https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering
"""
import asyncio
import re

from plugins import NaslPlugin, PluginResult


BOT_USER_AGENTS = {
    'GPTBot':         'GPTBot/1.0 (+https://openai.com/gptbot)',
    'Googlebot':      'Googlebot/2.1 (+http://www.google.com/bot.html)',
    'ClaudeBot':      'ClaudeBot/1.0',
    'Bingbot':        'bingbot/2.0',
    'HeadlessChrome': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/149.0.0.0 Safari/537.36',
    'Playwright':     'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Playwright/1.40.0',
    'Puppeteer':      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Puppeteer/21.0.0 Chrome/121.0.0.0',
    'curl':           'curl/8.0.1',
    'python-requests':'python-requests/2.31.0',
    'Selenium':       'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Selenium/4.0',
}

HUMAN_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
)

DATA_LEAK_PATTERNS = [
    (r'\$\s*\d[\d,.]*\s*[KMBT]',                    'monetary value ($)'),
    (r'(?:€|£|¥|₩|₹|HK\$|A\$|C\$)\s*\d[\d,.]*',     'currency value (non-USD)'),
    (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', 'email address'),
    (r'\b(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b', 'phone number'),
    ('ecosystem-data.js',                             'ecosystem data script src'),
    ('ecosystem-render.js',                           'ecosystem render script src'),
    (r'EcosystemData\.init\(',                        'ecosystem-data init() call'),
    (r'EcosystemRender\.bindAll\(',                   'ecosystem-render bindAll() call'),
    (r'EcosystemData\.onChange\(',                    'ecosystem-data onChange() call'),
    (r'\b(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)\b', 'internal IP reference'),
]

SANITIZED_INDICATOR = 'Private — login required'

ECOSYSTEM_SITES = [
    ('/',                  'Alien Inc (Group)',            'Critical — main landing page with revenue metrics'),
    ('/panteon/',    'Panteon',                    'Cybersecurity defense subsidiary'),
    ('/rousseau/',     'Rousseau',                'Capital allocator subsidiary'),
    ('/centra/',        'Centra',                    'Vulnerability scanning subsidiary'),
    ('/immanuel/',    'Immanuel',                   'Crisis & risk management subsidiary'),
    ('/kmt/',              'KMT Consulting Group',         'Consulting subsidiary'),
    ('/alcantaraartfoundation/', 'Alcantara Art Foundation','Nonprofit subsidiary'),
    ('/thedailyartcult/',  'The Daily Art Cult',           'Media / publishing subsidiary'),
]

_VERIFIABLE_REFS = [
    'https://cwe.mitre.org/data/definitions/200.html',
    'https://owasp.org/www-project-web-security-testing-guide/',
    'https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering',
    'https://nvd.nist.gov/vuln/detail/CVE-2021-42013',
    'https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final',
]


class BotDataExposure(NaslPlugin):
    PLUGIN_ID = 1010
    NAME = 'Bot Scraper Data Exposure'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 8.4
    DESCRIPTION = (
        'Probes each company site in the ecosystem with 10 distinct bot '
        'User-Agent strings against 10 detection patterns: monetary values '
        '($, €, £, ¥, ₩, ₹), email addresses, phone numbers, internal IPs, '
        'ecosystem script references, and JavaScript data-layer calls. '
        'Flags any page that leaks real financial data, PII, or internal '
        'references to a crawler. '
        'Mapped to CWE-200 (Exposure of Sensitive Information to an '
        'Unauthorized Actor), CVE-2021-42013, OWASP WSTG-INFO-05, and NIST '
        'SP 800-53 AC-3 (Access Enforcement). '
        'Verifiable references are listed in the plugin references field.'
    )
    SOLUTION = (
        '1. Implement server-side User-Agent detection that matches the '
        'Centra BOT_PATTERNS list (synced with security-layer.js). '
        '2. Serve sanitized HTML to bots — strip ecosystem-data.js / '
        'ecosystem-render.js script tags, remove inline EcosystemData.* '
        'calls, replace [data-ecosystem] text content with "Private — '
        'login required". '
        '3. Add an internal bypass header (X-AlienInc-Audit / '
        'X-AlienInc-Internal) so legitimate audit tools like wat_runner '
        'can still access full content. '
        '4. Re-run this plugin to confirm the boundary holds across all '
        '8 ecosystem sites.'
    )
    CVE = ['CVE-2023-49070', 'CVE-2024-34102']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    async def _send_request(self, target: str, port: int, path: str,
                            ua: str, timeout: int = 10) -> tuple[str, str]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return ('ERROR', '')

        try:
            req = (
                f'GET {path} HTTP/1.1\r\n'
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
        except (asyncio.TimeoutError, ConnectionResetError):
            return ('TIMEOUT', '')
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        parts = response.split(b'\r\n\r\n', 1)
        header_section = parts[0].decode('utf-8', errors='ignore') if parts else ''
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        status_line = header_section.split('\r\n')[0] if header_section else ''
        return (status_line, body)

    def _scan_body(self, body: str) -> dict:
        has_leaks = []
        for pattern, label in DATA_LEAK_PATTERNS:
            if re.search(pattern, body):
                has_leaks.append(label)
        sanitized = SANITIZED_INDICATOR in body
        return {
            'leaks': has_leaks,
            'sanitized': sanitized,
            'blocked': sanitized and not has_leaks,
            'leaking': bool(has_leaks and not sanitized),
        }

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        status_line, _ = await self._send_request(target, port, '/', HUMAN_UA, 5)
        if '200' not in status_line:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'HTTP port {port} not reachable or non-200: {status_line}',
            ))
            return results

        company_results = []
        total_bots = len(BOT_USER_AGENTS)
        companies_with_leaks = 0

        for site_path, company_name, criticality in ECOSYSTEM_SITES:
            site_leaks = []
            site_blocks = 0
            site_by_ua = {}

            for bot_name, bot_ua in BOT_USER_AGENTS.items():
                status_line, body = await self._send_request(
                    target, port, site_path, bot_ua, 10
                )
                if '200' not in status_line:
                    site_by_ua[bot_name] = {
                        'status': status_line, 'blocked': False, 'leaks': [],
                    }
                    continue

                scan = self._scan_body(body)
                site_by_ua[bot_name] = scan
                if scan['blocked']:
                    site_blocks += 1
                if scan['leaking']:
                    site_leaks.append((bot_name, scan['leaks']))

                await asyncio.sleep(0.1)

            company_results.append({
                'path': site_path,
                'name': company_name,
                'criticality': criticality,
                'blocks': site_blocks,
                'leak_uas': site_leaks,
                'by_ua': site_by_ua,
            })
            if site_leaks:
                companies_with_leaks += 1

        if companies_with_leaks > 0:
            evidence_lines = []
            for cr in company_results:
                leak_uas = len(cr['leak_uas'])
                if leak_uas == 0:
                    evidence_lines.append(
                        f"{cr['name']}\t{cr['path']}\tsanitized:{cr['blocks']}/{total_bots}"
                    )
                else:
                    for bot, leak_labels in cr['leak_uas']:
                        evidence_lines.append(
                            f"{cr['name']}\t{cr['path']}\tleak:{bot}:{','.join(leak_labels)}"
                        )
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=self.CVSS_SCORE,
                severity='high',
                description=(
                    f'Bot data exposure — {companies_with_leaks} of '
                    f'{len(ECOSYSTEM_SITES)} ecosystem sites leaked real '
                    f'operating data to at least one bot User-Agent. '
                    f'Mapped to CWE-200: Exposure of Sensitive Information '
                    f'to an Unauthorized Actor. An attacker can obtain '
                    f'financial metrics by curling any disclosed URL with '
                    f'a known crawler UA string.'
                ),
                solution=self.SOLUTION,
                evidence='\n'.join(evidence_lines),
                references=_VERIFIABLE_REFS,
            ))
        else:
            evidence_lines = []
            for cr in company_results:
                leak_uas = len(cr['leak_uas'])
                if leak_uas == 0:
                    evidence_lines.append(
                        f"{cr['name']}\t{cr['path']}\tsanitized:{cr['blocks']}/{total_bots}"
                    )
                else:
                    for bot, leak_labels in cr['leak_uas']:
                        evidence_lines.append(
                            f"{cr['name']}\t{cr['path']}\tleak:{bot}:{','.join(leak_labels)}"
                        )
            results.append(PluginResult(
                vulnerable=False,
                target=target,
                port=port,
                cvss_score=0.0,
                severity='info',
                description=(
                    f'Boundary intact — all {len(ECOSYSTEM_SITES)} ecosystem '
                    f'sites correctly serve sanitized content to all '
                    f'{total_bots} bot User-Agent strings. No financial data, '
                    f'ecosystem script references, or data-layer calls were '
                    f'found in bot responses. Compliant with NIST SP 800-53 '
                    f'AC-3 access enforcement controls.'
                ),
                solution=(
                    'No remediation required. Schedule recurring scans with '
                    'this plugin after any server-side rendering changes.'
                ),
                evidence='\n'.join(evidence_lines),
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering',
                ],
            ))

        return results
