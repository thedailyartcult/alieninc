"""
Plugin 1021: JavaScript Bot Detection Source Leak
===================================================
Scans JavaScript files loaded on the page for hardcoded bot
detection logic, honeypot paths, User-Agent regex patterns,
and internal IP references that could allow attackers to
reverse-engineer the bot detection and craft bypasses.

Real references:
  CWE-200   — Exposure of Sensitive Information
  CWE-538   — Insertion of Sensitive Information into Externally-Accessible File
  OWASP WSTG-INFO-05 — Review Web Page Content for Information Leakage
"""
import asyncio, re

from plugins import NaslPlugin, PluginResult


class JsBotDetectionLeak(NaslPlugin):
    PLUGIN_ID = 1021
    NAME = 'JavaScript Bot Detection Source Leak'
    FAMILY = 'Web Servers'
    CVSS_SCORE = 5.3
    DESCRIPTION = (
        'Scans client-side JavaScript for hardcoded bot detection logic, '
        'honeypot paths, UA regex patterns, security-layer URLs, and '
        'internal IP references. If attackers can read the bot detection '
        'rules in client-side JS, they can craft bypasses by avoiding '
        'known patterns or spoofing trusted UAs.'
    )
    SOLUTION = (
        '1. Move bot detection entirely server-side. Client-side JS '
        'should only collect signals, not enforce policy. '
        '2. Obfuscate or minify security-layer.js to hide UA patterns. '
        '3. Remove honeypot path enumeration from JavaScript — define '
        'them server-side only. '
        '4. Use server-side rate limiting rather than JS-based detection.'
    )
    CVE = ['CVE-2021-42013']
    PORTS = [80, 443, 8080]
    PLUGIN_TYPE = 'remote'

    LEAK_PATTERNS = {
        'bot UA regex': (
            r'(?:gptbot|googlebot|claudebot|headlesschrome|'
            r'playwright|puppeteer|selenium|bingbot|'
            r'curl|wget|nmap|sqlmap|phantomjs)',
            'Exposes which bot User-Agent patterns are detected. '
            'Attackers can avoid these UAs entirely.'
        ),
        'honeypot path': (
            r'(?:/admin/backup|/api/v1/secrets|'
            r'/\.env\.production|/config/database|/wp-content|/phpmyadmin|'
            r'/internal/audit|/\.git/config|/\.ssh/|/\.aws/)',
            'Lists honeypot/trap URLs that bots should avoid. '
            'Attackers learn which paths trigger detection.'
        ),
        'detection threshold': (
            r'(?:confidence|headlessIndicator|navigator\.webdriver|'
            r'callPhantom|__nightmare|plugins\.length|'
            r'languages\.length|WebGL.*renderer)',
            'Reveals bot detection thresholds and fingerprinting methods. '
            'Attackers can tune their tools to stay below thresholds.'
        ),
        'security-layer URL': (
            r'(?:injectHoneypots|enableAntiScraping|'
            r'enableSelfHealing|defenseState|hs-honeypots|'
            r'security-layer\.js)',
            'Exposes internal defense function names. '
            'Attackers can target or disable specific defenses.'
        ),
        'reconnaissance patterns': (
            r'(?:RECON_PATTERNS|\.git|\.env|wp-admin|xmlrpc|'
            r'swagger|graphql|\.sql\b|\.bak\b)',
            'Lists recon patterns that trigger alerts. '
            'Attackers learn which paths to avoid when scanning.'
        ),
        'internal IP/endpoint': (
            r'(?:localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|'
            r'supabase\.(?:co|in)|api\.alieninc|api/v\d+)',
            'Exposes internal infrastructure or API endpoints in JS source.'
        ),
    }

    async def _fetch(self, target, port, path, ua, timeout=8):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', '')

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
                if len(response) > 524288:
                    break
        except Exception:
            return ('TIMEOUT', '')
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        parts = response.split(b'\r\n\r\n', 1)
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        return ('200 OK' if b'200' in parts[0] else parts[0][:50].decode(errors='ignore'), body)

    async def check_target(self, target: str, port: int | None = 8080) -> list[PluginResult]:
        port = port or 8080
        results = []

        HUM = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

        # Get the human page to find JS file references
        s, html = await self._fetch(target, port, '/', HUM, 8)
        if '200' not in s:
            results.append(PluginResult(
                vulnerable=False, target=target, port=port,
                description=f'Cannot fetch page: {s[:50]}',
            ))
            return results

        # Helper: strip base64 strings to avoid false positives
        def strip_base64(content):
            return re.sub(
                r'"[A-Za-z0-9+/=]{40,}"',
                '"..."',
                content,
            )

        # Extract JS file URLs from <script src="..."> tags
        js_files = set(re.findall(r'<script\s[^>]*?src\s*=\s*["\']([^"\']+\.js)["\']', html, re.I))

        all_findings = []
        total_scanned = 0

        # Also check inline scripts (strip base64 first)
        inline_scripts = re.findall(r'<script[^>]*?>(.*?)</script>', html, re.DOTALL | re.I)
        for script_content in inline_scripts:
            if not script_content.strip():
                continue
            clean_content = strip_base64(script_content)
            for label, (pattern, explanation) in self.LEAK_PATTERNS.items():
                matches = re.findall(pattern, clean_content, re.I)
                if matches:
                    unique = sorted(set(matches))[:3]
                    all_findings.append((
                        'medium',
                        f'inline script → {label}: {", ".join(unique)}'
                    ))

        # Fetch each external JS file
        for js_url in js_files:
            path = js_url if js_url.startswith('/') else f'/{js_url}'
            if path.startswith('http'):
                continue  # skip CDN/external
            total_scanned += 1
            s, js_body = await self._fetch(target, port, path, HUM, 8)
            if '200' not in s:
                continue

            clean_body = strip_base64(js_body)

            for label, (pattern, explanation) in self.LEAK_PATTERNS.items():
                matches = re.findall(pattern, clean_body, re.I)
                if matches:
                    unique = sorted(set(matches))[:3]
                    all_findings.append((
                        'medium',
                        f'{path} → {label}: {", ".join(unique)} — {explanation[:80]}'
                    ))

            await asyncio.sleep(0.05)

        if all_findings:
            max_sev_level = 'medium'
            evidence = '\n'.join(d for _, d in all_findings[:15])
            results.append(PluginResult(
                vulnerable=True,
                target=target,
                port=port,
                cvss_score=5.3,
                severity=max_sev_level,
                description=(
                    f'JS source leak — {len(all_findings)} detection-related '
                    f'pattern(s) found across {total_scanned} external JS files '
                    f'and inline scripts. Attackers can reverse-engineer bot '
                    f'detection rules from client-side code.'
                ),
                solution=self.SOLUTION,
                evidence=evidence,
                references=[
                    'https://cwe.mitre.org/data/definitions/200.html',
                    'https://cwe.mitre.org/data/definitions/538.html',
                    'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/01-Information_Gathering/05-Review_Web_Page_Content_for_Information_Leakage',
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
                    f'No bot detection logic leaked in client-side JavaScript. '
                    f'Scanned {total_scanned} external JS files and inline scripts.'
                ),
                solution='No action required.',
                evidence=f'Scanned {total_scanned} external JS files.',
                references=[
                    'https://owasp.org/www-project-web-security-testing-guide/',
                ],
            ))

        return results
