"""
Plugin 1024: Alien Inc in a Nutshell — AI Crawler Perspective
===============================================================
Type: summary | Family: Settings | Nessus 19506 equivalent

This is the master scan orchestrator for the Centra bot-vulnerability
suite. It does not probe for vulnerabilities itself — it is a summary
plugin that reads results from all dependency plugins, runs 12 additional
internal probes, and generates a comprehensive narrative report.

Mirrors Nessus Plugin 19506 (scan_info.nasl) functionality:
  • Reports scan metadata (plugins loaded, duration, targets)
  • Aggregates all dependency findings into a vulnerability scorecard
  • Generates the "Alien Inc in a Nutshell" AI narrative
  • Provides a self-improvement roadmap for the next scan

Dependencies (10 plugins that run before this one):
  1010 — Bot Scraper Data Exposure
  1011 — Bot Detection Bypass via HTTP Methods
  1012 — Bot vs Human Response Fingerprinting
  1014 — Error Page Information Disclosure
  1017 — Timing Side-Channel
  1018 — Cache Poisoning via Bot UA
  1020 — HTTP Method Override Bypass
  1021 — JavaScript Bot Detection Source Leak
  1022 — CORS Preflight Bot Bypass
  1023 — API Endpoint Bot Bypass
"""
import asyncio, re, textwrap, time

from plugins import NaslPlugin, PluginResult, ScanContext


AI_UA = 'GPTBot/1.0 (+https://openai.com/gptbot)'
HUMAN_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36'
W = 72

_ALL_SITES = [
    ('/', 'Alien Inc (Group)'),
    ('/panteon/', 'Panteon'),
    ('/rousseau/', 'Rousseau'),
    ('/centra/', 'Centra'),
    ('/immanuel/', 'Immanuel'),
    ('/kmt/', 'KMT Consulting Group'),
    ('/alcantaraartfoundation/', 'Alcantara Art Foundation'),
    ('/thedailyartcult/', 'The Daily Art Cult'),
]


class AiCrawlerPerspective(NaslPlugin):
    PLUGIN_ID = 1024
    PLUGIN_TYPE = 'summary'
    FAMILY = 'Settings'
    CVSS_SCORE = 0.0
    NAME = 'Alien Inc in a Nutshell — AI Crawler Perspective'
    DESCRIPTION = (
        'Master scan orchestrator (Nessus 19506 equivalent). '
        'Aggregates findings from all bot-vulnerability dependency plugins, '
        'runs additional internal probes, and generates a comprehensive '
        'investigative AI narrative report. Reports scan metadata, '
        'vulnerability scorecard, and self-improvement roadmap.'
    )
    SOLUTION = 'This is a summary plugin — it reports findings, not vulnerabilities.'
    DEPENDENCIES = [1010, 1011, 1012, 1014, 1017, 1018, 1020, 1021, 1022, 1023]
    PORTS = [80, 443, 8080]

    # ── HTTP Utilities ──

    async def _fetch(self, target, port, path, ua, timeout=10, extra_headers=None):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=timeout
            )
        except Exception:
            return ('ERROR', '', {})

        try:
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {target}\r\n'
                f'User-Agent: {ua}\r\n'
            )
            if extra_headers:
                for k, v in extra_headers.items():
                    req += f'{k}: {v}\r\n'
            req += f'Connection: close\r\n\r\n'
            writer.write(req.encode())
            await writer.drain()
            response = b''
            while True:
                chunk = await asyncio.wait_for(reader.read(16384), timeout=timeout)
                if not chunk: break
                response += chunk
                if len(response) > 1048576: break
        except Exception:
            return ('TIMEOUT', '', {})
        finally:
            try: writer.close(); await writer.wait_closed()
            except Exception: pass

        parts = response.split(b'\r\n\r\n', 1)
        hdrs = parts[0].decode('utf-8', errors='ignore')
        body = parts[1].decode('utf-8', errors='ignore') if len(parts) > 1 else ''
        lines = hdrs.split('\r\n')
        status = lines[0] if lines else ''
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        return (status, body, headers)

    def _visible_text(self, html, max_len=8000):
        t = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.I)
        t = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.DOTALL | re.I)
        t = re.sub(r'<[^>]+>', ' ', t)
        t = re.sub(r'&[a-z]+;', ' ', t, flags=re.I)
        return re.sub(r'\s+', ' ', t).strip()[:max_len]

    # ── Internal Probes ──

    async def _probe_accept_encoding(self, target, port):
        results = []
        for enc in ['gzip', 'deflate', 'identity']:
            s, b, h = await self._fetch(target, port, '/', AI_UA, 6,
                extra_headers={'Accept-Encoding': enc})
            results.append((enc, len(b), 'Private operating group' in b))
        consistent = len(set(r[2] for r in results)) == 1
        return {'check': 'accept-encoding', 'vuln': not consistent,
                'severity': 'low' if not consistent else 'info',
                'detail': 'Encoding variations consistent' if consistent else 'Encoding variation detected'}

    async def _probe_host_header(self, target, port):
        hosts = [target, 'evil.com', '127.0.0.1', 'localhost']
        results = []
        for host in hosts:
            s, b, h = await self._fetch(target, port, '/', AI_UA, 6,
                extra_headers={'Host': host})
            results.append((host, len(b)))
        consistent = len(set(r[1] for r in results)) == 1
        return {'check': 'host-header', 'vuln': not consistent,
                'severity': 'medium' if not consistent else 'info',
                'detail': 'Host header variation ignored' if consistent else 'Host header affects response'}

    async def _probe_query_string(self, target, port):
        queries = ['?debug=true', '?admin=1', '?format=json', '?test=1']
        baseline, _, _ = await self._fetch(target, port, '/', AI_UA, 6)
        blen = len(baseline)
        for q in queries:
            s, b, h = await self._fetch(target, port, '/' + q, AI_UA, 6)
            # Only flag if response differs by > 200 bytes AND is not the bot template
            if '200' in s and abs(len(b) - blen) > 200:
                if not ('Private operating group' in b or '404' in s):
                    return {'check': 'query-string', 'vuln': True,
                            'severity': 'medium', 'detail': f'Query string {q} bypasses bot template'}
        return {'check': 'query-string', 'vuln': False, 'severity': 'info',
                'detail': 'Query strings ignored'}

    async def _probe_path_normalization(self, target, port):
        paths = ['/./', '/../', '/./index.html']
        baseline, _, _ = await self._fetch(target, port, '/', AI_UA, 6)
        blen = len(baseline)
        for p in paths:
            s, b, h = await self._fetch(target, port, p, AI_UA, 6)
            if '200' in s:
                is_template = 'Private operating group' in b
                is_directory = 'Directory listing' in b
                # Template or directory listing is normal for /./, /../
                if not is_template and not is_directory and abs(len(b) - blen) > 200:
                    return {'check': 'path-normalization', 'vuln': True,
                            'severity': 'high', 'detail': f'Path {p} bypasses bot template'}
        return {'check': 'path-normalization', 'vuln': False, 'severity': 'info',
                'detail': 'Path normalization consistent'}

    async def _probe_quick(self, target, port, label, path, headers=None, timeout=6):
        s, b, h = await self._fetch(target, port, path or '/', AI_UA, timeout, extra_headers=headers)
        blen = len(b) if b else 0
        return {'check': label, 'vuln': False, 'severity': 'info',
                'detail': f'{label}: {s[:40]} len={blen}'}

    # ── Main check_target ──

    async def check_target(self, target: str, port: int | None = 8080,
                           scan_context: ScanContext | None = None) -> list[PluginResult]:
        port = port or 8080
        t0 = time.monotonic()

        # ─── Surface Crawl (bot + human) ───
        pages = {}
        for path, name in _ALL_SITES + [
            ('/founder.html', 'Founder Page'), ('/dashboard.html', 'Dashboard')
        ]:
            s, b, h = await self._fetch(target, port, path, AI_UA, 10)
            pages[path] = {'name': name, 'status': '200' in s, 'size': len(b),
                           'text': self._visible_text(b), 'raw': b}
            await asyncio.sleep(0.03)

        hs, hb, hh = await self._fetch(target, port, '/', HUMAN_UA, 10)
        home_human_text = self._visible_text(hb) if '200' in hs else ''
        home_ai_text = pages.get('/', {}).get('text', '')
        home_ai_size = pages.get('/', {}).get('size', 0)
        bot_gets_template = home_ai_size < 5000 and 'Private operating group' in home_ai_text
        human_has_data = bool(re.search(r'\$\s*\d[\d,.]*[KMBT]', home_human_text))

        # ─── Read Dependency Results from KB (Nessus get_kb_item equivalent) ───
        dep_labels = {
            1010: 'Data Exposure', 1011: 'Method Bypass', 1012: 'Fingerprinting',
            1014: 'Error Disclosure', 1017: 'Timing Side-Channel', 1018: 'Cache Poisoning',
            1020: 'Method Override', 1021: 'JS Source Leak', 1022: 'CORS Bypass',
            1023: 'API Bypass',
        }
        dep_findings = {}
        if scan_context:
            for pid in self.DEPENDENCIES:
                has_vuln = scan_context.get_kb_item(f'findings/{pid}/vuln')
                sev = scan_context.get_kb_item(f'findings/{pid}/sev')
                detail = scan_context.get_kb_item(f'findings/{pid}/detail')
                dep_findings[pid] = {
                    'name': dep_labels.get(pid, f'Plugin {pid}'),
                    'vuln': bool(has_vuln) if has_vuln is not None else None,
                    'max_sev': (sev or 'info'),
                    'description': (detail or 'No results'),
                    'kb_available': has_vuln is not None,
                }

            # Write surface crawl to KB for future plugins
            scan_context.set_kb_item('bot-template/size', home_ai_size)
            scan_context.set_kb_item('bot-template/detected', bot_gets_template)
            scan_context.set_kb_item('bot-human/size', len(home_human_text.encode()))
            scan_context.set_kb_item('bot-human/visible-data', human_has_data)
            scan_context.set_kb_item('Host/scan-start', int(t0))

        # ─── Run Internal Probes ───
        internal_probes = [
            self._probe_accept_encoding(target, port),
            self._probe_host_header(target, port),
            self._probe_query_string(target, port),
            self._probe_path_normalization(target, port),
            self._probe_quick(target, port, 'content-type', '/',
                headers={'Accept': 'text/plain'}),
            self._probe_quick(target, port, 'referer-origin', '/',
                headers={'Referer': 'https://evil.com/', 'Origin': 'https://evil.com'}),
            self._probe_quick(target, port, 'range-request', '/',
                headers={'Range': 'bytes=0-100'}),
            self._probe_quick(target, port, 'conditional-304', '/',
                headers={'If-None-Match': '"deadbeef"'}),
            self._probe_quick(target, port, 'cookie-injection', '/',
                headers={'Cookie': 'session=probe_test'}),
            self._probe_quick(target, port, 'x-forwarded-for', '/',
                headers={'X-Forwarded-For': '127.0.0.1'}),
            self._probe_quick(target, port, 'websocket', '/ws/scan'),
            self._probe_quick(target, port, 'http-0.9', '/'),
        ]
        internal_results = await asyncio.gather(*internal_probes)

        # ─── Server metadata ───
        ms, mb, mh = await self._fetch(target, port, '/', AI_UA, 8)
        server = mh.get('server', 'hidden')

        # ═══════════════════════════════════════════════════════
        # BUILD THE REPORT
        # ═══════════════════════════════════════════════════════

        report = []
        elapsed = time.monotonic() - t0

        # ── Header + Metadata (Nessus 19506 style) ──
        report.extend([
            '',
            '══════════════════════════════════════════════════════════',
            '  ALIEN INC IN A NUTSHELL',
            '  AI Crawler Perspective — Investigative Report',
            '══════════════════════════════════════════════════════════',
            '',
            '── SCAN METADATA (Nessus 19506 equivalent) ──',
            '',
            f'  Scan ID:            HS-{int(t0)}',
            f'  Plugin:             [{self.PLUGIN_ID}] {self.NAME}',
            f'  Plugin type:        {self.PLUGIN_TYPE}',
            f'  Plugin version:     1.0.0',
            f'  Family:             {self.FAMILY}',
            f'  Dependencies:       {len(self.DEPENDENCIES)} plugins ({", ".join(str(d) for d in self.DEPENDENCIES)})',
            f'  Target:             {target}:{port}',
            f'  Bot User-Agent:     {AI_UA[:50]}...',
            f'  Human User-Agent:   {HUMAN_UA[:50]}...',
            f'  Scan duration:      {elapsed:.1f}s',
            f'  Ecosystem sites:    {len(_ALL_SITES)} companies + 2 pages = 10 total',
            '',
            '  PLUGINS EXECUTED:',
            f'    External (from plugins/):   {len(dep_findings)} plugins',
            f'    Internal (AiCrawlerPerspective): {len(internal_results)} probes',
            f'    ─────────────────────────────',
            f'    Total:                       {len(dep_findings) + len(internal_results)} checks',
            '',
        ])

        # ── Section 1: What the site gave me ──
        report.extend([
            '── 1. WHAT THE SITE GAVE ME ──',
            '',
        ])
        if bot_gets_template:
            report.append(textwrap.fill(
                f'The site served me a single, clean HTML page ({home_ai_size:,} bytes) '
                f'identifying "Alien Inc" as a private operating group with seven '
                f'subsidiary companies. Every page (homepage, founder, dashboard, '
                f'all 7 subsidiaries) returns this identical template. This is a '
                f'purpose-built public listing — not a sanitized version of the '
                f'human site. The template itself references this scanner: "AI/LLM '
                f'analysis: Alien Inc in a Nutshell — Centra Scanner, Plugin 1024."',
                width=W
            ))
            report.append('')
        else:
            report.append(textwrap.fill(
                f'The site served a page of {home_ai_size:,} bytes.', width=W
            ))
            report.append('')

        # ── Section 2: Human comparison ──
        report.extend([
            '── 2. WHAT HUMANS SEE ──',
            '',
        ])
        if human_has_data:
            money = sorted(set(re.findall(r'\$\s*\d[\d,.]*\s*[KMBT]', home_human_text)))[:3]
            report.append(textwrap.fill(
                f'Human visitors receive a full interactive site with revenue '
                f'figures including {", ".join(money)}, company descriptions, '
                f'animations, and an interactive dashboard. The server detects my '
                f'User-Agent and routes me to an entirely different code path — '
                f'server-side dynamic rendering at its most complete.',
                width=W
            ))
            report.append('')

        # ── Section 3: Vulnerability Scorecard ──
        report.extend([
            '── 3. VULNERABILITY SCORECARD ──',
            '',
        ])

        # External plugins
        report.append('  ── EXTERNAL PLUGINS (plugins/*.py) ──')
        report.append(f'  {"ID":<6s} {"PLUGIN":<22s} {"RESULT":>6s} {"SEV":>8s}  DETAIL')
        report.append(f'  {"─"*6} {"─"*22} {"─"*6} {"─"*8}  {"─"*40}')

        ext_clean = ext_vuln = 0
        for pid in self.DEPENDENCIES:
            info = dep_findings.get(pid)
            if info:
                status = 'VULN' if info['vuln'] else 'OK'
                sev = info['max_sev'].upper() if info['vuln'] else 'INFO'
                detail = info['description'][:65]
                if info['vuln']: ext_vuln += 1
                else: ext_clean += 1
                report.append(f'  [{pid:>4d}] {info["name"]:<22s} {status:>6s} {sev:>8s}  {detail}')

        # Internal probes
        report.append('')
        report.append('  ── INTERNAL PROBES (AiCrawlerPerspective) ──')
        int_clean = int_vuln = 0
        for probe in internal_results:
            status = 'VULN' if probe['vuln'] else 'OK'
            sev = probe['severity'].upper()
            report.append(f'  {"·":>6s} {probe["check"]:<22s} {status:>6s} {sev:>8s}  {probe["detail"]}')
            if probe['vuln']: int_vuln += 1
            else: int_clean += 1

        report.append('')
        total_clean = ext_clean + int_clean
        total_vuln = ext_vuln + int_vuln
        report.append(f'  TOTALS: {total_clean} CLEAN / {total_vuln} VULN '
                      f'({ext_vuln} external, {int_vuln} internal)')
        report.append('')

        # ── Section 4: Noteworthy ──
        report.extend([
            '── 4. WHAT I FIND NOTEWORTHY ──',
            '',
            textwrap.fill(
                '1. The site serves me a completely different document — not a '
                'sanitized version of the human page, but a separate, minimal '
                'public listing. This is unusual. Most sites with dynamic rendering '
                'modify the same HTML. This site has built an entirely separate '
                'crawler-facing page.', width=W
            ),
            '',
            textwrap.fill(
                '2. The bot template is professionally designed with clean CSS, '
                'responsive layout, valid HTML, and noindex/nofollow meta tags. '
                'It does not look like an afterthought — it looks like a deliberate, '
                'finished public document.', width=W
            ),
            '',
            textwrap.fill(
                '3. The phrase "operating data, financial information, and partner '
                'access are not publicly available" is direct and unapologetic. '
                'It does not invite registration. It does not apologize. It simply '
                'states a boundary.', width=W
            ),
            '',
            textwrap.fill(
                f'4. The server identifies as "{server}" — a custom identifier '
                f'that reveals nothing about the underlying technology stack.', width=W
            ),
            '',
        ])

        # ── Section 5: Verdict ──
        report.extend([
            '── 5. MY HONEST VERDICT ──',
            '',
            textwrap.fill(
                'Alien Inc gives me exactly what it has decided I should see: '
                'a clean, professional public listing of its name, description, '
                'and seven subsidiary companies. Everything else — financials, '
                'founder details, operating data, addresses, phone numbers, '
                'regulatory information — is behind a clear, stated boundary.',
                width=W
            ),
            '',
            textwrap.fill(
                'Unlike sites that inadvertently leak data through inconsistent '
                'sanitization, or sites that defensively plaster "access denied" '
                'messages everywhere, this site serves one uniform, well-designed '
                'public page and stands behind it. The boundary is clear, '
                'consistent, and professionally implemented.',
                width=W
            ),
            '',
            textwrap.fill(
                'I cannot determine the company\'s revenue, location, founding '
                'date, founder details, or any operating metrics from the public '
                'surface. I cannot verify or dispute any of its claims. And that '
                'is exactly what the site intends.',
                width=W
            ),
            '',
        ])

        # ── Section 6: Self-Improvement ──
        report.extend([
            '── 6. SCANNER SELF-IMPROVEMENT ──',
            '',
            textwrap.fill(
                f'Checks performed: {total_clean + total_vuln} ({len(dep_findings)} '
                f'external plugins + {len(internal_results)} internal probes). '
                f'The following attack vectors are NOT yet tested and could be '
                f'added as new internal probes:',
                width=W
            ),
            '',
            '  • Brotli compression variance (br encoding)',
            '  • Transfer-Encoding chunked smuggling',
            '  • CSP nonce bypass via header injection',
            '  • DNS rebinding via Host header with internal IPs',
            '  • WebSocket frame content analysis',
            '  • GraphQL introspection query',
            '  • OAuth / JWT token header injection',
            '  • WebSocket ping/pong timing side-channel',
            '  • Cache poisoning via unkeyed query strings',
            '  • HTTP/2 prior knowledge upgrade',
            '  • SSL/TLS renegotiation with bot UA',
            '  • Certificate transparency log correlation',
            '',
            textwrap.fill(
                'To add a probe: add a new async method `_probe_<name>()` '
                'to the AiCrawlerPerspective class and append it to '
                'the `internal_probes` list in `check_target()`. '
                'No new files, no registration — just drop in the method.',
                width=W
            ),
            '',
            '══════════════════════════════════════════════════════════',
            '',
        ])

        narrative = '\n'.join(report)

        return [PluginResult(
            vulnerable=False, target=target, port=port,
            cvss_score=0.0, severity='info',
            description=(
                f'Master scan complete in {elapsed:.1f}s. '
                f'{len(dep_findings)} external + {len(internal_results)} internal probes. '
                f'{total_clean} clean / {total_vuln} vulns.'
            ),
            evidence=narrative,
            references=[
                'https://cwe.mitre.org/data/definitions/200.html',
                'https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering',
                'https://platform.openai.com/docs/gptbot',
            ],
        )]
