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
import urllib.request
import http.server
import socketserver
import os
import threading
import hashlib
import hmac

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
    'panteon':      os.path.join(ROOT, 'panteon'),
    'kmt':          os.path.join(ROOT, 'kmt'),
    'stalcantara':  os.path.join(ROOT, 'stalcantarafoundation'),
    'sp':           os.path.join(ROOT, 'sp'),
    'secure':       os.path.join(ROOT, 'secure'),
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


# ── Secure gate ─────────────────────────────────────────────
# Every detected bot (Wayback Machine included) is served the secure
# gate page instead of real content, so archived snapshots capture the
# authentication wall. The same page fronts secure.alieninc.tech.

SECURE_GATE_CANDIDATES = [
    os.path.join(ROOT, 'secure', 'index.html'),
    os.path.join(ROOT, 'secure.html'),
]

SECURE_ERROR_CALLOUT = (
    '<div class="lpf_call_out_error" role="alert"><span>'
    '<span class="t">Authentication failed</span>'
    'The login or the password is incorrect.'
    '</span></div>'
)

_gate_cache = {'path': None, 'mtime': 0, 'html': None}


def _load_gate_page():
    """Read the canonical gate page from disk (cached by mtime)."""
    for p in SECURE_GATE_CANDIDATES:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if _gate_cache['path'] == p and _gate_cache['mtime'] == m and _gate_cache['html'] is not None:
            return _gate_cache['html']
        try:
            with open(p, 'r', encoding='utf-8') as f:
                html = f.read()
        except OSError:
            continue
        _gate_cache['path'] = p
        _gate_cache['mtime'] = m
        _gate_cache['html'] = html
        return html
    return None


def is_bot(user_agent):
    if not user_agent:
        return False
    ua = user_agent.lower()
    for pattern in BOT_PATTERNS:
        if re.search(pattern, ua):
            return True
    return False


# ── Secure gate authentication ──────────────────────────────
# Authenticates users for the secure.alieninc.tech subdomain.
# Default backend: Supabase Auth (GoTrue password grant) using the same
# project as The Daily Art Cult. Falls back to env credentials if configured.
# Nothing else changes — the session cookie and vault/moderation gate
# all keep working on top of this verifier.

SECURE_AUTH_BACKEND = os.environ.get('SECURE_AUTH_BACKEND', 'supabase')
SUPABASE_URL = os.environ.get(
    'SUPABASE_URL',
    'https://frwjaixxlgthkgjtafhz.supabase.co'
)
SUPABASE_ANON_KEY = os.environ.get(
    'SUPABASE_ANON_KEY',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZyd2phaXh4bGd0aGtnanRhZmh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDUzNDQsImV4cCI6MjA5NDYyMTM0NH0.j2DKz__QMml4WplMYNmsQpTUw0qu-kZG7Md3qBEEdEc'
)
# Set to "true" to require app_metadata.secure_access == true for login.
SUPABASE_REQUIRE_ACCESS = os.environ.get('SUPABASE_REQUIRE_ACCESS', 'false').lower() in ('1', 'true', 'yes')

# Path to moderation guidelines data (outside the git repo on production).
# Defaults to secure/moderation/data/ inside the repo for local dev.
MODERATION_DATA_PATH = os.environ.get(
    'MODERATION_DATA_PATH',
    os.path.join(ROOT, 'secure', 'moderation', 'data')
)

# Ecosystem JSON is read from the repo's data/ directory (never served directly).
# Cannot be overridden — always uses the repo path for consistency.
ECOSYSTEM_JSON_PATH = os.path.join(ROOT, 'data', 'alieninc-ecosystem.json')

SECURE_SESSION_COOKIE = 'secure_session'
MAIN_SESSION_COOKIE = 'alieninc_session'
SECURE_SESSION_TTL = 8 * 3600  # 8 hours

_session_secret_ephemeral = None

# Moderation audit log: in-memory ring of recent accesses.
MODERATION_AUDIT_LOG = []
MODERATION_AUDIT_MAX = 5000
MODERATION_AUDIT_PATH = os.path.join(ROOT, 'secure', 'moderation-audit.log')

# Simple in-memory rate limiter: IP → list of timestamps (rolling window).
_rate_limiter = {}

RATE_LIMIT_WINDOW = 60       # seconds
RATE_LIMIT_MAX = 30          # max requests per window per IP for moderation


def _log_moderation_audit(action, user, remote_ip, path, detail=''):
    entry = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'action': action,
        'user': user,
        'ip': remote_ip,
        'path': path,
        'detail': detail,
    }
    MODERATION_AUDIT_LOG.append(entry)
    if len(MODERATION_AUDIT_LOG) > MODERATION_AUDIT_MAX:
        MODERATION_AUDIT_LOG[:] = MODERATION_AUDIT_LOG[-MODERATION_AUDIT_MAX:]
    try:
        with open(MODERATION_AUDIT_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass


def _check_rate_limit(ip):
    now = time.time()
    window = now - RATE_LIMIT_WINDOW
    if ip not in _rate_limiter:
        _rate_limiter[ip] = []
    timestamps = _rate_limiter[ip]
    # Purge old entries
    _rate_limiter[ip] = [t for t in timestamps if t > window]
    if len(_rate_limiter[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limiter[ip].append(now)
    return True


def _session_secret():
    global _session_secret_ephemeral
    s = os.environ.get('SECURE_SESSION_SECRET', '')
    if s:
        return s.encode('utf-8')
    if _session_secret_ephemeral is None:
        # Ephemeral per-boot secret: sessions invalidate on restart (fail-safe).
        _session_secret_ephemeral = os.urandom(32)
    return _session_secret_ephemeral


def verify_secure_credentials(user, password):
    if not user or not password:
        return False
    if SECURE_AUTH_BACKEND == 'supabase':
        return _verify_via_supabase(user, password)
    gate_user = os.environ.get('SECURE_GATE_USER', '')
    gate_pass = os.environ.get('SECURE_GATE_PASS', '')
    if not gate_user or not gate_pass:
        return False  # fail closed
    return (hmac.compare_digest(user.encode('utf-8'), gate_user.encode('utf-8'))
            and hmac.compare_digest(password.encode('utf-8'), gate_pass.encode('utf-8')))


def _verify_via_supabase(email, password):
    """GoTrue password grant against Supabase Auth."""
    url = '%s/auth/v1/token?grant_type=password' % SUPABASE_URL.rstrip('/')
    payload = json.dumps({'email': email, 'password': password}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'apikey': SUPABASE_ANON_KEY,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode('utf-8'))
            sys.stderr.write('[SUPABASE-AUTH] error: %s\n' % body)
        except Exception:
            sys.stderr.write('[SUPABASE-AUTH] HTTP error: %s\n' % e.code)
        return False
    except Exception as e:
        sys.stderr.write('[SUPABASE-AUTH] request failed: %s\n' % e)
        return False

    access_token = data.get('access_token')
    if not access_token:
        return False

    if SUPABASE_REQUIRE_ACCESS:
        user = data.get('user', {})
        metadata = user.get('app_metadata', {}) or user.get('user_metadata', {}) or {}
        if not metadata.get('secure_access'):
            sys.stderr.write('[SUPABASE-AUTH] access denied for %r (no secure_access metadata)\n' % email)
            return False

    return True


def _issue_secure_session(user):
    expiry = int(time.time()) + SECURE_SESSION_TTL
    payload = '%d.%s' % (expiry, user)
    sig = hmac.new(_session_secret(), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return payload + '.' + sig


def _check_secure_session(token):
    if not token:
        return False
    try:
        expiry_s, rest = token.split('.', 1)
        _user, sig = rest.rsplit('.', 1)
        expiry = int(expiry_s)
    except (ValueError, AttributeError):
        return False
    if time.time() > expiry:
        return False
    expected = hmac.new(_session_secret(), ('%d.%s' % (expiry, _user)).encode('utf-8'),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _safe_redirect(path):
    """Prevent open redirects by only allowing local paths."""
    if not path:
        return None
    path = path.split('?', 1)[0].split('#', 1)[0]
    if not path.startswith('/'):
        return None
    # Disallow protocol-relative URLs and double slashes
    if path.startswith('//'):
        return None
    return path


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

        # /moderation/ is ONLY accessible via secure.alieninc.tech (its files live
        # under secure/moderation/ and resolve naturally from the secure subdomain root).
        if words and words[0] == 'moderation' and not self._is_secure_host():
            return os.path.join(ROOT, '.nonexistent')

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
            self.headers.get('X-AlienInc-Internal', '').lower() == 'panteon'
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
            os.path.join(ROOT, 'secure', 'vault'),
            os.path.join(ROOT, 'secure', 'moderation'),
            os.path.join(ROOT, 'panteon', 'engine'),
            os.path.join(ROOT, 'panteon', 'plugins'),
            os.path.join(ROOT, 'sp', 'engine'),
            os.path.join(ROOT, 'thedailyartcult', 'supabase'),
        ]
        translated_lower = translated.lower().rstrip('/')
        for d in sensitive_dirs:
            d_lower = d.lower()
            if translated_lower == d_lower or translated_lower.startswith(d_lower + '/'):
                return True
        return False

    def _serve_secure_gate(self, error=False, label='secure-gate'):
        html = _load_gate_page()
        if html is None:
            self.send_error(404)
            return
        if error:
            html = html.replace('<!--SECURE_ERROR-->', SECURE_ERROR_CALLOUT, 1)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        sys.stderr.write('[BOT] %s — %s (%s)\n' % (
            self.address_string(), self.path, label,
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

    def _is_secure_host(self):
        host = self.headers.get('Host', '').split(':')[0].lower()
        return host == 'secure.alieninc.tech'

    def _is_vault_path(self, path):
        path = path.split('?', 1)[0]
        return path == '/vault' or path.startswith('/vault/')

    def _is_moderation_path(self, path):
        path = path.split('?', 1)[0]
        return path == '/moderation' or path.startswith('/moderation/')

    def _has_valid_secure_session(self):
        cookie = self.headers.get('Cookie', '')
        token = None
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith(SECURE_SESSION_COOKIE + '='):
                token = part.split('=', 1)[1]
                break
        return _check_secure_session(token)

    def _has_valid_main_session(self):
        cookie = self.headers.get('Cookie', '')
        token = None
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith(MAIN_SESSION_COOKIE + '='):
                token = part.split('=', 1)[1]
                break
        return _check_secure_session(token)

    def _is_ecosystem_data_path(self, path):
        lower = path.lower().split('?', 1)[0].split('#', 1)[0]
        return lower == '/data/alieninc-ecosystem.json'

    def _is_ecosystem_js_path(self, path):
        lower = path.lower().split('?', 1)[0].split('#', 1)[0]
        return lower in ('/data/ecosystem-data.js', '/data/ecosystem-render.js')

    def _embed_ecosystem_data(self, html, authenticated):
        placeholder = '/*[ECOSYSTEM_DATA]*/'
        if placeholder not in html:
            return html
        if authenticated and os.path.isfile(ECOSYSTEM_JSON_PATH):
            try:
                with open(ECOSYSTEM_JSON_PATH, 'r', encoding='utf-8') as f:
                    data_json = f.read()
            except OSError:
                data_json = 'null'
        else:
            data_json = 'null'
        return html.replace(placeholder, 'var ECOSYSTEM_DATA = ' + data_json + ';', 1)

    def do_POST(self):
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        if path == '/pxpadmin/bin/authform.cgi':
            self._handle_secure_auth()
            return
        if path == '/api/login':
            self._handle_api_login()
            return
        self.send_error(404)

    def _handle_api_login(self):
        """JSON-based login for the main-site overlay.  Returns JSON, never a redirect."""
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            length = 0
        length = min(length, 65536)
        raw = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else ''
        ctype = self.headers.get('Content-Type', '')
        if 'application/json' in ctype:
            try:
                body = json.loads(raw)
                user = (body.get('email', '') or '').strip()
                password = body.get('password', '') or ''
            except (json.JSONDecodeError, TypeError):
                user = ''
                password = ''
        else:
            try:
                form = urllib.parse.parse_qs(raw, keep_blank_values=True)
            except Exception:
                form = {}
            user = (form.get('user', [''])[0] or '').strip()
            password = form.get('password', [''])[0] or ''
        if not user or not password:
            self._send_json_error('Email and password required')
            return
        if verify_secure_credentials(user, password):
            token = _issue_secure_session(user)
            domain = self.headers.get('Host', '').split(':')[0].lower()
            base = '.alieninc.tech'
            def c(k, v):
                sd = '; Domain=' + base if domain.endswith('alieninc.tech') else ''
                return '%s=%s; Path=/; HttpOnly; Secure; SameSite=Lax%s' % (k, v, sd)
            self.send_response(200)
            self.send_header('Set-Cookie', c(SECURE_SESSION_COOKIE, token))
            self.send_header('Set-Cookie', c(MAIN_SESSION_COOKIE, token))
            self._send_json({'ok': True})
        else:
            self._send_json_error('Invalid login credentials')

    def _send_json(self, data):
        body = json.dumps(data).encode('utf-8')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _send_json_error(self, msg):
        self.send_response(200)
        self._send_json({'ok': False, 'error': msg})

    def _handle_secure_auth(self):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            length = 0
        length = min(length, 65536)
        raw = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else ''
        try:
            form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        except Exception:
            form = {}
        user = (form.get('user', [''])[0] or '').strip()
        password = form.get('password', [''])[0] or ''
        # Optional post-auth redirect; default to root (safe for any host).
        default_redirect = '/'
        redirect = _safe_redirect(form.get('next', [''])[0]) or default_redirect
        if verify_secure_credentials(user, password):
            token = _issue_secure_session(user)
            self.send_response(302)
            self.send_header('Location', redirect)
            domain = self.headers.get('Host', '').split(':')[0].lower()
            base_domain = '.alieninc.tech'
            if domain.endswith('alieninc.tech'):
                self.send_header('Set-Cookie',
                                 SECURE_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; Secure; SameSite=Lax; Domain=' + base_domain)
                self.send_header('Set-Cookie',
                                 MAIN_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; Secure; SameSite=Lax; Domain=' + base_domain)
            else:
                self.send_header('Set-Cookie',
                                 SECURE_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; Secure; SameSite=Lax')
                self.send_header('Set-Cookie',
                                 MAIN_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; Secure; SameSite=Lax')
            self.end_headers()
            sys.stderr.write('[SECURE-AUTH] success user=%r redirect=%r from %s\n' % (
                user, redirect, self.address_string(),
            ))
            return
        sys.stderr.write('[SECURE-AUTH] fail user=%r from %s\n' % (
            user, self.address_string(),
        ))
        self._serve_secure_gate(error=True, label='auth-fail')

    def _is_moderation_data_path(self, path):
        path = path.split('?', 1)[0]
        return path.startswith('/moderation/data/') or path == '/moderation/data'

    def _check_secure_access(self):
        """Verify the request is allowed for protected paths.
        Returns True if the request may proceed, False if a response was already sent."""
        if self._is_moderation_path(self.path) and not self._is_secure_host():
            self.send_error(404)
            return False
        if self._is_secure_host() and (self._is_vault_path(self.path) or self._is_moderation_path(self.path)):
            if not self._has_valid_secure_session():
                sys.stderr.write('[SECURE-GATE] %s — %s (no session, redirected)\n' % (
                    self.address_string(), self.path,
                ))
                self.send_response(302)
                self.send_header('Location', '/')
                self.end_headers()
                return False
        # Block direct access to moderation data files — data is only served
        # embedded in the HTML by _serve_moderation_page.
        if self._is_moderation_data_path(self.path):
            _log_moderation_audit('DATA-BLOCK', '-', self.address_string(), self.path, 'Direct data path blocked')
            self.send_error(404)
            return False
        return True

    def do_HEAD(self):
        if self.path.startswith('/api/'):
            super().do_HEAD()
            return
        if self._is_blocked_path(self.path):
            self.send_error(404)
            return
        if not self._check_secure_access():
            return
        if self._is_moderation_path(self.path):
            ip = self.client_address[0] if self.client_address else '?'
            if not _check_rate_limit(ip):
                self.send_error(429)
                return
        super().do_HEAD()

    def end_headers(self):
        if self._is_moderation_path(self.path) or self._is_vault_path(self.path):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

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
        elif self.path == '/api/ecosystem' or self.path.startswith('/api/ecosystem?'):
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self.send_error(404)
                return
            self._serve_ecosystem_api()
        elif self.path == '/pxpadmin/bin/authform.cgi' or self.path.startswith('/pxpadmin/bin/authform.cgi?'):
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            if self._is_blocked_path(self.path):
                self.send_error(404)
                return
            # Direct access to the ecosystem JSON is always blocked.
            # Data is only available via server-side embedding or the
            # authenticated /api/ecosystem endpoint.
            if self._is_ecosystem_data_path(self.path):
                self.send_error(404)
                return
            if not self._check_secure_access():
                return
            # Serve moderation page with data embedded server-side
            # (must run before sensitive-directory check since moderation dir
            #  is listed there — we want /moderation/ to serve the page, not 404)
            if self._is_moderation_path(self.path):
                ip = self.client_address[0] if self.client_address else '?'
                if not _check_rate_limit(ip):
                    _log_moderation_audit('RATE-LIMIT', '-', ip, self.path)
                    self.send_error(429)
                    return
                self._serve_moderation_page()
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
                        self._serve_secure_gate(label='bot')
                        return
                except Exception as e:
                    sys.stderr.write('[BOT-ERR] %s\n' % str(e))
            try:
                fs_path = self.translate_path(self.path)
                if os.path.isdir(fs_path):
                    fs_path = os.path.join(fs_path, 'index.html')
                if os.path.isfile(fs_path) and fs_path.endswith('.html'):
                    base = os.path.basename(fs_path)
                    if base == 'index.html' or base == 'dashboard.html':
                        self._serve_html_with_ecosystem(fs_path)
                        return
            except Exception:
                pass
            super().do_GET()

    def _serve_moderation_page(self):
        """Serve moderation index.html with guidelines data embedded server-side.
        No separate data endpoint exists — data is injected into the HTML."""
        html_path = os.path.join(ROOT, 'secure', 'moderation', 'index.html')
        data_path = os.path.join(MODERATION_DATA_PATH, 'guidelines.json')
        if not os.path.isfile(html_path):
            self.send_error(404)
            return
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html = f.read()
        except OSError:
            self.send_error(404)
            return
        placeholder = '/*[GUIDELINES_DATA]*/'
        if placeholder in html:
            if os.path.isfile(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        data_json = f.read()
                except OSError:
                    data_json = 'null'
            else:
                data_json = 'null'
            # NOTE: placeholder is already inside a <script> block — no wrapping tags
            html = html.replace(placeholder, 'var GUIDELINES_DATA = ' + data_json + ';', 1)
        user = self._get_session_user()
        ip = self.client_address[0] if self.client_address else '?'
        _log_moderation_audit('PAGE-SERVE', user or '-', ip, self.path)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_html_with_ecosystem(self, fs_path):
        auth = self._has_valid_secure_session() or self._has_valid_main_session()
        try:
            with open(fs_path, 'r', encoding='utf-8') as f:
                html = f.read()
        except OSError:
            self.send_error(404)
            return
        html = self._embed_ecosystem_data(html, auth)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, private')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_ecosystem_api(self):
        if not os.path.isfile(ECOSYSTEM_JSON_PATH):
            self.send_error(404)
            return
        try:
            with open(ECOSYSTEM_JSON_PATH, 'r', encoding='utf-8') as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        body = data.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _get_session_user(self):
        cookie = self.headers.get('Cookie', '')
        for part in cookie.split(';'):
            part = part.strip()
            if part.startswith(SECURE_SESSION_COOKIE + '='):
                token = part.split('=', 1)[1]
                try:
                    return token.split('.', 1)[1].rsplit('.', 1)[0]
                except (IndexError, ValueError):
                    return None
        return None

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


# ── Local testing config ──────────────────────────────────
# Drop local_config.py in this directory for localhost testing.
# It monkey-patches _is_secure_host and _get_host_root so
# http://localhost:8080/ behaves like secure.alieninc.tech.
# The file is gitignored and never pushed to production.
if __name__ == '__main__':
    try:
        import local_config  # noqa: F401
    except ImportError:
        pass
    import concurrent.futures
    print(f'\n  Alien Inc — http://localhost:{PORT}')
    print(f'  ─────────────────────────────────────')
    print(f'  Dashboard:    /dashboard.html')
    print(f'  Competitors:  /api/competitors')
    print(f'  Prices:       /api/prices')
    print(f'  Secure gate:  secure.alieninc.tech (bots → gate page)')
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
