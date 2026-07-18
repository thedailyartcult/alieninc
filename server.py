#!/usr/bin/env python3
"""
Alien Inc — integrated server.
Serves all static files + proxies live market data from Yahoo Finance.
This is THE way to serve the Alien Inc dashboard.

Usage:
    python3 server.py          # default port 8080
    python3 server.py 3000     # custom port
"""

import sys
import json
import re
import time
import urllib.parse
import http.server
import socketserver
import os
import threading

try:
    import yfinance as yf
except ImportError:
    yf = None
    print('[YF] yfinance not installed — pip install yfinance')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
ROOT = os.path.dirname(os.path.abspath(__file__))

SUBDOMAIN_ROOTS = {
    '1609':         os.path.join(ROOT, '1609holdings'),
    'exosphere':    os.path.join(ROOT, 'exosphere'),
    'hawksight':    os.path.join(ROOT, 'hawksight'),
    'kmt':          os.path.join(ROOT, 'kmt'),
    'stalcantara':  os.path.join(ROOT, 'stalcantarafoundation'),
    'sp':           os.path.join(ROOT, 'sp'),
}

_cache = {'data': None, 'ts': 0, 'lock': threading.Lock()}
CACHE_TTL = 21600  # 6 hours

COMPANIES = [
    {'ticker': 'BRK-B',    'name': 'Berkshire Hathaway', 'industry': 'Conglomerate',                'hq': 'Omaha, Nebraska',     'founded': 1969, 'note': 'Diversified conglomerate — closest model'},
    {'ticker': '005930.KS', 'name': 'Samsung Electronics', 'industry': 'Technology / Electronics',   'hq': 'Suwon, South Korea',  'founded': 1938, 'note': 'Largest Korean chaebol'},
    {'ticker': 'GOOGL',     'name': 'Alphabet',          'industry': 'Technology',                   'hq': 'Mountain View, CA',   'founded': 1998, 'note': 'Search, AI, cloud, autonomous'},
    {'ticker': 'META',      'name': 'Meta Platforms',    'industry': 'Technology / Social',          'hq': 'Menlo Park, CA',      'founded': 2004, 'note': 'Social, AI, metaverse'},
    {'ticker': 'KPMG',      'name': 'KPMG',              'industry': 'Professional Services',        'hq': 'Amsterdam, Netherlands', 'founded': 1987, 'note': 'Big Four accounting — private partnership'},
    {'ticker': '023530.KS', 'name': 'Lotte Shopping',    'industry': 'Retail / Conglomerate',        'hq': 'Seoul, South Korea',  'founded': 1979, 'note': 'Lotte Group listed subsidiary'},
]

# ADR tickers where Yahoo financials are in local currency, not USD
LOCAL_CURRENCY_ADRS = {}

# Published financials for private companies (from annual reports)
PRIVATE_DATA = {
    'KPMG': {
        'revenue': 38400000000,
        'netIncome': None,
        'ebitda': None,
        'marketCap': None,
        'pe': None,
        'note': 'Big Four accounting — private partnership. Revenue from KPMG International Annual Report FY2025.',
    },
}


BOT_PATTERNS = [
    r'bot', r'crawler', r'spider', r'scraper', r'harvester',
    r'curl', r'wget', r'python-requests', r'go-http-client',
    r'java/', r'perl', r'ruby', r'php/',
    r'nmap', r'nikto', r'sqlmap', r'nessus', r'openvas',
    r'acunetix', r'burp', r'wpscan', r'dirbuster', r'ffuf',
    r'gobuster', r'feroxbuster', r'wfuzz',
    r'headlesschrome', r'headlessfirefox', r'phantomjs',
    r'playwright', r'puppeteer', r'selenium',
    r'gptbot', r'chatgpt-user', r'ccbot', r'anthropic',
    r'claudebot', r'google-extended', r'bytespider',
    r'omgilibot', r'facebookbot', r'petalbot',
]


BOT_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Alien Inc — Private Operating Group</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1.5rem; line-height: 1.6; color: #1a1a1a; background: #fff; }
  h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: 0.25rem; }
  .tagline { font-size: 0.95rem; color: #666; margin-bottom: 2rem; }
  h2 { font-size: 0.85rem; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.04em; margin: 2rem 0 0.75rem 0; }
  .sub { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.4rem 2rem; }
  .sub-item { font-size: 0.9rem; padding: 0.3rem 0; }
  .sub-name { font-weight: 500; }
  .sub-desc { color: #666; font-size: 0.82rem; }
  .notice { margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid #eee; font-size: 0.85rem; color: #888; }
  footer { margin-top: 3rem; font-size: 0.75rem; color: #aaa; }
</style>
</head>
<body>
<h1>Alien Inc</h1>
<p class="tagline">Private operating group.</p>
<h2>Subsidiary Companies</h2>
<div class="sub">
<div class="sub-item"><span class="sub-name">The Daily Art Cult</span> <span class="sub-desc">— Digital media and publishing</span></div>
<div class="sub-item"><span class="sub-name">Hawksight</span> <span class="sub-desc">— Cybersecurity and exposure management</span></div>
<div class="sub-item"><span class="sub-name">1609 Holdings</span> <span class="sub-desc">— Capital allocation and governance</span></div>
<div class="sub-item"><span class="sub-name">KMT Consulting Group</span> <span class="sub-desc">— Strategy and applied AI</span></div>
<div class="sub-item"><span class="sub-name">Exosphere</span> <span class="sub-desc">— Acquisitions and succession advisory</span></div>
<div class="sub-item"><span class="sub-name">St. Alcantara Foundation</span> <span class="sub-desc">— Cultural preservation</span></div>
<div class="sub-item"><span class="sub-name">Statute &amp; Precedent</span> <span class="sub-desc">— Legal and compliance</span></div>
</div>
<div class="notice">
This is a private company. Operating data, financial information, and partner access are not publicly available.
</div>
<div class="notice" style="border-top:none;padding-top:0.5rem;margin-top:0.5rem;font-size:0.78rem;color:#aaa;">
AI/LLM analysis: <em>Alien Inc in a Nutshell</em> &mdash; Hawksight Scanner, Plugin 1024
</div>
<footer>&copy; Alien Inc</footer>
</body>
</html>'''


def is_bot(user_agent):
    if not user_agent:
        return False
    ua = user_agent.lower()
    for pattern in BOT_PATTERNS:
        if re.search(pattern, ua):
            return True
    return False


def _empty_item(co):
    return {
        'name': co['name'], 'ticker': co['ticker'],
        'industry': co['industry'], 'hq': co['hq'],
        'founded': co['founded'], 'note': co['note'],
        'marketCap': None, 'revenue': None, 'netIncome': None,
        'ebitda': None, 'pe': None, 'price': None,
        'ccy': 'USD', 'eps': None, 'volume': None,
        'asOf': None, 'status': 'unavailable',
        'previousClose': None, 'priceChange': None, 'priceChangePct': None,
        'dayHigh': None, 'dayLow': None,
    }


def fetch_competitor_data():
    now = time.time()
    with _cache['lock']:
        if _cache['data'] and (now - _cache['ts']) < CACHE_TTL:
            return _cache['data']

    if not yf:
        return {
            'competitors': [_empty_item(co) for co in COMPANIES],
            'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'source': 'Yahoo Finance — yfinance not installed',
            'error': 'pip install yfinance'
        }

    results = []
    for co in COMPANIES:
        item = _empty_item(co)
        try:
            t = yf.Ticker(co['ticker'])
            info = t.info
            item['price'] = info.get('currentPrice') or info.get('regularMarketPrice')
            item['previousClose'] = info.get('regularMarketPreviousClose') or info.get('previousClose')
            item['dayHigh'] = info.get('regularMarketDayHigh') or info.get('dayHigh')
            item['dayLow'] = info.get('regularMarketDayLow') or info.get('dayLow')
            item['marketCap'] = info.get('marketCap')
            item['pe'] = info.get('trailingPE')
            item['eps'] = info.get('trailingEps')
            item['revenue'] = info.get('totalRevenue')
            item['netIncome'] = info.get('netIncomeToCommon')
            item['ebitda'] = info.get('ebitda')
            item['volume'] = info.get('volume')
            item['shares'] = info.get('sharesOutstanding')
            item['fwdPE'] = info.get('forwardPE')
            item['yahooCcy'] = info.get('currency', 'USD')
            item['exchange'] = info.get('exchange', '')

            # Detect ADRs where Yahoo financials are in local currency
            # Price/market cap are in USD (ADR), but revenue/net income are in local currency
            local_ccy = LOCAL_CURRENCY_ADRS.get(co['ticker'])
            item['ccy'] = info.get('currency', 'USD')
            item['financialCcy'] = local_ccy or item['ccy']

            if item['price'] is not None or item['marketCap'] is not None:
                item['status'] = 'live'
                item['asOf'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                if item['price'] is not None and item['previousClose'] is not None:
                    item['priceChange'] = round(item['price'] - item['previousClose'], 2)
                    if item['previousClose'] != 0:
                        item['priceChangePct'] = round((item['priceChange'] / item['previousClose']) * 100, 2)
            else:
                print(f'[YF] {co["ticker"]}: no data returned')
        except Exception as e:
            print(f'[YF] {co["ticker"]}: {e}')

        # Override with published data for private companies
        priv = PRIVATE_DATA.get(co['ticker'])
        if priv:
            for k, v in priv.items():
                if v is not None:
                    item[k] = v
            item['status'] = 'private'
            item['asOf'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

        results.append(item)
        time.sleep(0.5)

    data = {
        'competitors': results,
        'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source': 'Yahoo Finance via yfinance'
    }

    with _cache['lock']:
        _cache['data'] = data
        _cache['ts'] = time.time()

    live = sum(1 for r in results if r['status'] == 'live')
    print(f'[YF] Fetched {live}/{len(results)} competitors')
    return data


SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://www.britishmuseum.org https://www.metmuseum.org; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://www.britishmuseum.org https://cdn.tailwindcss.com https://unpkg.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.britishmuseum.org https://cdn.tailwindcss.com https://unpkg.com https://consent.cookiebot.com; connect-src 'self' https://*.supabase.co https://*.supabase.in wss://*.supabase.co; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'",
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Vary': 'User-Agent',
    'Permissions-Policy': 'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
    'X-Compliance': 'monitored; CIS-NGINX-v3.0; DISA-STIG-V4R5; PCI-DSS-v4.0.1; OWASP-ASVS-L1; NIST-800-53-Moderate; NIST-CSF-2.0; report=/compliance.html',
}


_price_cache = {'data': None, 'ts': 0, 'lock': threading.Lock()}
PRICE_CACHE_TTL = 60  # 1 minute

def fetch_prices():
    now = time.time()
    with _price_cache['lock']:
        if _price_cache['data'] and (now - _price_cache['ts']) < PRICE_CACHE_TTL:
            return _price_cache['data']

    prices = []
    if yf:
        for co in COMPANIES:
            priv = PRIVATE_DATA.get(co['ticker'])
            if priv:
                continue
            entry = {'ticker': co['ticker'], 'name': co['name'], 'ccy': 'USD',
                     'price': None, 'previousClose': None,
                     'priceChange': None, 'priceChangePct': None,
                     'dayHigh': None, 'dayLow': None, 'asOf': None}
            try:
                t = yf.Ticker(co['ticker'])
                info = t.info
                entry['price'] = info.get('currentPrice') or info.get('regularMarketPrice')
                entry['previousClose'] = info.get('regularMarketPreviousClose') or info.get('previousClose')
                entry['dayHigh'] = info.get('regularMarketDayHigh') or info.get('dayHigh')
                entry['dayLow'] = info.get('regularMarketDayLow') or info.get('dayLow')
                entry['ccy'] = info.get('currency', 'USD')
                if entry['price'] is not None and entry['previousClose'] is not None:
                    entry['priceChange'] = round(entry['price'] - entry['previousClose'], 2)
                    if entry['previousClose'] != 0:
                        entry['priceChangePct'] = round((entry['priceChange'] / entry['previousClose']) * 100, 2)
                entry['asOf'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            except Exception as e:
                print(f'[Prices] {co["ticker"]}: {e}')
            prices.append(entry)
            time.sleep(0.2)

    data = {'prices': prices, 'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    with _price_cache['lock']:
        _price_cache['data'] = data
        _price_cache['ts'] = time.time()
    return data


class AlienHandler(http.server.SimpleHTTPRequestHandler):
    server_version = 'AlienInc'
    sys_version = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        for header, value in SECURITY_HEADERS.items():
            self.send_header(header, value)
        super().end_headers()

    def _get_host_root(self):
        host = self.headers.get('Host', '')
        hostname = host.split(':')[0].lower()
        if hostname in ('localhost', '127.0.0.1', ''):
            return ROOT
        if hostname == 'alieninc.tech' or hostname == 'www.alieninc.tech':
            return ROOT
        if hostname.endswith('.alieninc.tech'):
            sub = hostname.replace('.alieninc.tech', '')
            if sub in SUBDOMAIN_ROOTS:
                return SUBDOMAIN_ROOTS[sub]
        return ROOT

    def translate_path(self, path):
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = os.path.normpath(path)
        words = path.split('/')
        words = list(filter(None, words))
        root = self._get_host_root()
        filepath = root
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            filepath = os.path.join(filepath, word)
        if trailing_slash:
            filepath += '/'
        return filepath

    def _is_internal_scanner(self):
        return (
            self.headers.get('X-AlienInc-Internal', '').lower() == 'hawksight'
            or self.headers.get('X-AlienInc-Audit', '').lower() == 'statute'
        )

    def _is_localhost(self):
        return self.client_address and self.client_address[0] in ('127.0.0.1', '::1', 'localhost')

    def _is_blocked_path(self, path):
        blocked_patterns = [
            r'\.git/',
            r'\.git$',
            r'\.backups/',
            r'\.bak$',
            r'\.bak\.',
            r'\.backup$',
            r'\.backup\.',
            r'\.old$',
            r'\.old\.',
            r'\.swp$',
            r'\.db$',
            r'\.db-shm$',
            r'\.db-wal$',
            r'\.db-lock$',
            r'\.sqlite$',
            r'\.sql$',
            r'\.md$',
            r'\.edpb-wat/',
            r'\.aider\.',
            r'\.angular/',
            r'\.py$',
            r'\.ts$',
            r'\.env',
            r'\.DS_Store$',
            r'Thumbs\.db$',
            r'\.idea/',
            r'\.vscode/',
            r'wp-admin/',
            r'wp-content/',
            r'wp-login',
            r'xmlrpc',
            r'phpmyadmin',
            r'server-status',
            r'server-info',
            r'\.ssh/',
            r'\.aws/',
            r'actuator/',
            r'druid/',
            r'vendor/phpunit',
            r'storage/logs',
            r'adminer',
            r'/console$',
        ]
        lower = path.lower()
        for pattern in blocked_patterns:
            if re.search(pattern, lower):
                return True
        return False

    def _is_sensitive_directory(self, path):
        translated = self.translate_path(path)
        sensitive_dirs = [
            os.path.join(ROOT, 'data'),
            os.path.join(ROOT, 'hawksight', 'engine'),
            os.path.join(ROOT, 'hawksight', 'plugins'),
            os.path.join(ROOT, 'sp', 'engine'),
            os.path.join(ROOT, 'thedailyartcult', 'supabase'),
        ]
        translated_lower = translated.lower().rstrip('/')
        for d in sensitive_dirs:
            d_lower = d.lower()
            if translated_lower == d_lower or translated_lower.startswith(d_lower + '/'):
                return True
        return False

    def _serve_bot_template(self):
        body = BOT_TEMPLATE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        sys.stderr.write('[BOT] %s — %s (template)\n' % (
            self.address_string(), self.path,
        ))
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_empty_json(self, label):
        data = json.dumps({}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        sys.stderr.write('[BOT-API] %s — %s (blocked %s)\n' % (
            self.address_string(), self.path, label,
        ))
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def _serve_bot_robotstxt(self):
        body = (
            'User-agent: *\n'
            'Allow: /\n'
            'Disallow: /partner/\n'
            'Disallow: /internal/\n'
            'Disallow: /data/\n'
            'Disallow: /api/\n'
            'Disallow: /login/\n'
            'Disallow: /admin/\n'
            'Disallow: /dashboard.\n'
            'Disallow: /founder.\n'
            '\n'
            '# Alien Inc — Registered Partner Access Required\n'
            '# Public pages are crawlable. Operating data, founder\n'
            '# details, and financials require partner authentication.\n'
            '# Crawl-delay: 10\n'
            '\n'
            'Sitemap: https://alieninc.com/sitemap.xml\n'
        ).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        sys.stderr.write('[BOT] %s — robots.txt (blocked)\n' % self.address_string())
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _is_bot_data_path(self, path):
        lower = path.lower()
        data_patterns = [
            '/data/alieninc-ecosystem.json',
            '/data/ecosystem-data.js',
            '/data/ecosystem-render.js',
            '/data/competitors.js',
            '/data/exchange-rates.js',
            '/robots.txt',
            '/sitemap.xml',
            '/alieninc-sitemap.md',
        ]
        for pattern in data_patterns:
            if lower == pattern or lower.startswith(pattern):
                return True
        return False

    def do_GET(self):
        if self.path == '/api/competitors' or self.path.startswith('/api/competitors?'):
            ua = self.headers.get('User-Agent', '')
            if is_bot(ua) and not self._is_internal_scanner() and not self._is_localhost():
                self._serve_empty_json('competitors')
                return
            self._serve_competitors()
        elif self.path == '/api/prices' or self.path.startswith('/api/prices?'):
            ua = self.headers.get('User-Agent', '')
            if is_bot(ua) and not self._is_internal_scanner() and not self._is_localhost():
                self._serve_empty_json('prices')
                return
            self._serve_prices()
        else:
            if self._is_blocked_path(self.path):
                self.send_error(404)
                return
            if self.path.endswith('/') and self._is_sensitive_directory(self.path):
                self.send_error(404)
                return
            ua = self.headers.get('User-Agent', '')
            if is_bot(ua) and not self._is_internal_scanner() and not self._is_localhost():
                if self._is_bot_data_path(self.path):
                    if '/robots.txt' in self.path or '/sitemap' in self.path:
                        self._serve_bot_robotstxt()
                    else:
                        self._serve_empty_json('data file')
                    return
                try:
                    fs_path = self.translate_path(self.path)
                    if os.path.isdir(fs_path):
                        fs_path = os.path.join(fs_path, 'index.html')
                    if os.path.isfile(fs_path) and fs_path.endswith('.html'):
                        self._serve_bot_template()
                        return
                except Exception as e:
                    sys.stderr.write('[BOT-ERR] %s\n' % str(e))
            try:
                fs_path = self.translate_path(self.path)
                if os.path.isdir(fs_path):
                    fs_path = os.path.join(fs_path, 'index.html')
                if os.path.isfile(fs_path) and fs_path.endswith('.html'):
                    pass  # already handled above for bots
            except Exception:
                pass
            super().do_GET()

    def _serve_prices(self):
        if 'flush=1' in self.path:
            with _price_cache['lock']:
                _price_cache['data'] = None
                _price_cache['ts'] = 0
        data = fetch_prices()
        body = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_competitors(self):
        if 'flush=1' in self.path:
            with _cache['lock']:
                _cache['data'] = None
                _cache['ts'] = 0
            print('[API] Cache flushed — forcing fresh fetch')
        data = fetch_competitor_data()
        body = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        path = str(args[0]) if args else ''
        if '/api/' in path:
            sys.stderr.write('[API] %s - %s\n' % (self.address_string(), format % args))


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    import concurrent.futures
    print(f'\n  Alien Inc — http://localhost:{PORT}')
    print(f'  ─────────────────────────────────────')
    print(f'  Dashboard:    /dashboard.html')
    print(f'  Competitors:  /api/competitors')
    print(f'  Prices:       /api/prices')
    print(f'  All files:    /')
    print(f'  ─────────────────────────────────────\n')

    import threading
    def _warmup():
        print('[YF] Pre-warming competitor data...')
        try:
            d = fetch_competitor_data()
            live = sum(1 for c in d.get('competitors', []) if c.get('status') == 'live')
            private = sum(1 for c in d.get('competitors', []) if c.get('status') == 'private')
            print(f'[YF] Ready — {live}/{private + live} competitors live, {private} private')
        except Exception as e:
            print(f'[YF] Pre-warm failed: {e}')
        print('[YF] Pre-warming price data...')
        try:
            fetch_prices()
            print('[YF] Prices ready')
        except Exception as e:
            print(f'[YF] Price pre-warm failed: {e}')

    t = threading.Thread(target=_warmup, daemon=True)
    t.start()

    with ReusableTCPServer(('', PORT), AlienHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down.')
            httpd.shutdown()
