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
    'rousseau':         os.path.join(ROOT, 'rousseau'),
    'panteon':          os.path.join(ROOT, 'panteon'),
    'centra':           os.path.join(ROOT, 'centra'),
    'kmt':              os.path.join(ROOT, 'kmt'),
    'immanuel':         os.path.join(ROOT, 'immanuel'),
    'alcantaraartfoundation': os.path.join(ROOT, 'alcantaraartfoundation'),
    'sp':               os.path.join(ROOT, 'sp'),
    'secure':           os.path.join(ROOT, 'secure'),
}

_cache = {'data': None, 'ts': 0, 'lock': threading.Lock()}
CACHE_TTL = 21600  # 6 hours

_rate_limit = {'attempts': {}, 'lock': threading.Lock()}
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60

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


def _sanitize_html_for_bots(html):
    """Strip sensitive data from HTML served to bot user agents."""
    sanitized = html
    sanitized = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        'Private — login required', sanitized
    )
    sanitized = re.sub(
        r'(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
        'Private — login required', sanitized
    )
    sanitized = re.sub(
        r'\$\s*[\d,]+(?:\.\d+)?\s*[KMBT]?(?:illion|illion)?',
        'Private — login required', sanitized
    )
    sanitized = re.sub(
        r'€\s*[\d,]+(?:\.\d+)?',
        'Private — login required', sanitized
    )
    sanitized = re.sub(
        r'£\s*[\d,]+(?:\.\d+)?',
        'Private — login required', sanitized
    )
    sanitized = re.sub(
        r'<script[^>]*src=["\'](?:data/)?ecosystem-data\.js["\'][^>]*>',
        '<!-- ecosystem-data.js removed -->', sanitized
    )
    sanitized = re.sub(
        r'<script[^>]*src=["\'](?:data/)?ecosystem-render\.js["\'][^>]*>',
        '<!-- ecosystem-render.js removed -->', sanitized
    )
    sanitized = re.sub(
        r'EcosystemData\.init\([^)]*\)',
        '/* Private — login required */', sanitized
    )
    sanitized = re.sub(
        r'EcosystemRender\.bindAll\([^)]*\)',
        '/* Private — login required */', sanitized
    )
    sanitized = re.sub(
        r'EcosystemData\.onChange\([^)]*\)',
        '/* Private — login required */', sanitized
    )
    sanitized = re.sub(
        r'var\s+ECOSYSTEM_DATA\s*=\s*\{[^}]*\}',
        'var ECOSYSTEM_DATA = null', sanitized
    )
    sanitized = re.sub(
        r'var\s+ECOSYSTEM_DATA\s*=\s*[^;]+;',
        'var ECOSYSTEM_DATA = null;', sanitized
    )
    return sanitized


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
ECOSYSTEM_DB_PATH = os.path.join(ROOT, 'db', 'ecosystem.db')

_engine_cache = {}

def _get_ecosystem_from_db():
    try:
        if not os.path.isfile(ECOSYSTEM_DB_PATH):
            return None
        if 'engine' not in _engine_cache:
            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            sys.path.insert(0, os.path.join(ROOT, 'db'))
            from ecosystem_engine import EcosystemEngine
            _engine_cache['engine'] = EcosystemEngine(db_path=ECOSYSTEM_DB_PATH)
        engine = _engine_cache['engine']
        return engine.get_ecosystem_json()
    except Exception as e:
        sys.stderr.write('[ECO] DB read failed: %s — falling back to static JSON\n' % e)
        return None

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

    def _get_subdomain(self):
        host = self.headers.get('Host', '')
        hostname = host.split(':')[0].lower()
        if hostname in ('localhost', '127.0.0.1', '', 'alieninc.tech', 'www.alieninc.tech'):
            return None
        if hostname.endswith('.alieninc.tech'):
            return hostname.replace('.alieninc.tech', '')
        return None

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
        if self.path in ('/pxpadmin/bin/authform.cgi', '/api/login'):
            self._add_rate_limit_headers()
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

    def _is_secure_connection(self):
        return self.headers.get('X-Forwarded-Proto', '').lower() == 'https'

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
        if authenticated:
            data = _get_ecosystem_from_db()
            if data:
                data_json = json.dumps(data, default=str)
            elif os.path.isfile(ECOSYSTEM_JSON_PATH):
                try:
                    with open(ECOSYSTEM_JSON_PATH, 'r', encoding='utf-8') as f:
                        data_json = f.read()
                except OSError:
                    data_json = 'null'
            else:
                data_json = 'null'
        else:
            data_json = 'null'
        return html.replace(placeholder, 'var ECOSYSTEM_DATA = ' + data_json + ';', 1)

    def do_POST(self):
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        auth_paths = ('/pxpadmin/bin/authform.cgi', '/api/login')
        if path in auth_paths:
            ip = self.client_address[0] if self.client_address else 'unknown'
            now = time.time()
            with _rate_limit['lock']:
                if ip not in _rate_limit['attempts']:
                    _rate_limit['attempts'][ip] = []
                _rate_limit['attempts'][ip] = [t for t in _rate_limit['attempts'][ip] if now - t < RATE_LIMIT_WINDOW]
                count = len(_rate_limit['attempts'][ip])
                if count >= RATE_LIMIT_MAX:
                    self.send_response(429)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('X-RateLimit-Limit', str(RATE_LIMIT_MAX))
                    self.send_header('X-RateLimit-Remaining', '0')
                    self.send_header('X-RateLimit-Reset', str(int(now + RATE_LIMIT_WINDOW)))
                    self.send_header('Retry-After', str(RATE_LIMIT_WINDOW))
                    self.end_headers()
                    self.wfile.write(b'{"error":"rate limit exceeded"}')
                    return
                _rate_limit['attempts'][ip].append(now)
        if path == '/pxpadmin/bin/authform.cgi':
            self._handle_secure_auth()
            return
        if path == '/api/login':
            self._handle_api_login()
            return
        if path == '/api/simulation/run':
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self.send_error(403)
                return
            self._handle_simulation_run()
            return
        if path.startswith('/api/admin/'):
            if self._get_subdomain() is not None:
                self.send_error(404)
                return
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self._send_json({"error": "authentication required"}, 401)
                return
            self._handle_admin_post(path)
            return
        if path.startswith('/api/panteon/'):
            if self._get_subdomain() != 'panteon':
                self.send_error(404)
                return
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self._send_json({"error": "authentication required"}, 401)
                return
            self._handle_panteon_post(path)
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
            secure_flag = '; Secure' if self._is_secure_connection() else ''
            def c(k, v):
                sd = '; Domain=' + base if domain.endswith('alieninc.tech') else ''
                return '%s=%s; Path=/; HttpOnly; SameSite=Lax%s%s' % (k, v, secure_flag, sd)
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
        password = (form.get('password', [''])[0] or '')
        default_redirect = '/'
        redirect = _safe_redirect(form.get('next', [''])[0]) or default_redirect
        if verify_secure_credentials(user, password):
            token = _issue_secure_session(user)
            self.send_response(302)
            self._add_rate_limit_headers()
            self.send_header('Location', redirect)
            domain = self.headers.get('Host', '').split(':')[0].lower()
            base_domain = '.alieninc.tech'
            secure_flag = '; Secure' if self._is_secure_connection() else ''
            if domain.endswith('alieninc.tech'):
                self.send_header('Set-Cookie',
                                 SECURE_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; SameSite=Lax; Domain=' + base_domain + secure_flag)
                self.send_header('Set-Cookie',
                                 MAIN_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; SameSite=Lax; Domain=' + base_domain + secure_flag)
            else:
                self.send_header('Set-Cookie',
                                 SECURE_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; SameSite=Lax' + secure_flag)
                self.send_header('Set-Cookie',
                                 MAIN_SESSION_COOKIE + '=' + token +
                                 '; Path=/; HttpOnly; SameSite=Lax' + secure_flag)
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
            if is_bot(ua) and not self._is_internal_scanner():
                self._serve_empty_json('competitors')
                return
            self._serve_competitors()
        elif self.path == '/api/prices' or self.path.startswith('/api/prices?'):
            ua = self.headers.get('User-Agent', '')
            if is_bot(ua) and not self._is_internal_scanner():
                self._serve_empty_json('prices')
                return
            self._serve_prices()
        elif self.path == '/api/ecosystem' or self.path.startswith('/api/ecosystem?'):
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self.send_error(404)
                return
            self._serve_ecosystem_api()
        elif self.path == '/api/simulation/status' or self.path.startswith('/api/simulation/status?'):
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self.send_error(404)
                return
            self._serve_simulation_status()
        elif self.path == '/api/admin/state' or self.path.startswith('/api/admin/state?'):
            if self._get_subdomain() is not None:
                self.send_error(404)
                return
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self._send_json({"error": "authentication required"}, 401)
                return
            self._serve_admin_state()
        elif self.path == '/api/admin/audit' or self.path.startswith('/api/admin/audit?'):
            if self._get_subdomain() is not None:
                self.send_error(404)
                return
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self._send_json({"error": "authentication required"}, 401)
                return
            self._serve_admin_audit()
        elif self.path.startswith('/api/panteon/'):
            if self._get_subdomain() != 'panteon':
                self.send_error(404)
                return
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self._send_json({"error": "authentication required"}, 401)
                return
            self._handle_panteon_api(self.path)
        elif self.path == '/api/compliance/status' or self.path.startswith('/api/compliance/status?'):
            self._handle_compliance_status()
        elif self.path == '/api/compliance/report' or self.path.startswith('/api/compliance/report?'):
            self._handle_compliance_report()
        elif self.path == '/console' or self.path.startswith('/console/'):
            auth = self._has_valid_secure_session() or self._has_valid_main_session()
            if not auth:
                self.send_error(401)
                return
            self._serve_console_page()
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
            if is_bot(ua) and not self._is_internal_scanner():
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
                        self._serve_sanitized_html(fs_path)
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

    def _serve_sanitized_html(self, fs_path):
        """Serve HTML with sensitive data stripped for bot user agents."""
        try:
            with open(fs_path, 'r', encoding='utf-8') as f:
                html = f.read()
        except OSError:
            self.send_error(404)
            return
        html = _sanitize_html_for_bots(html)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, private')
        self.end_headers()
        sys.stderr.write('[BOT-SANITIZE] %s — %s\n' % (
            self.address_string(), self.path,
        ))
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_ecosystem_api(self):
        data = _get_ecosystem_from_db()
        if data:
            raw = json.dumps(data, default=str)
        elif os.path.isfile(ECOSYSTEM_JSON_PATH):
            try:
                with open(ECOSYSTEM_JSON_PATH, 'r', encoding='utf-8') as f:
                    raw = f.read()
            except OSError:
                self.send_error(404)
                return
        else:
            self.send_error(404)
            return
        body = raw.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_simulation_status(self):
        try:
            if not os.path.isfile(ECOSYSTEM_DB_PATH):
                self._send_json({"error": "ecosystem database not initialized"}, 404)
                return
            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            from ecosystem_engine import EcosystemEngine
            engine = EcosystemEngine(db_path=ECOSYSTEM_DB_PATH)
            state = engine.get_state()
            body = json.dumps(state, default=str).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_simulation_run(self):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else '{}'
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            days = min(int(body.get('days', 1)), 90)

            if not os.path.isfile(ECOSYSTEM_DB_PATH):
                self._send_json({"error": "ecosystem database not initialized"}, 404)
                return

            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            from ecosystem_engine import EcosystemEngine
            engine = EcosystemEngine(db_path=ECOSYSTEM_DB_PATH)

            if days == 1:
                result = engine.simulate_day()
            else:
                results = engine.simulate_period(days)
                result = results[-1] if results else None

            state = engine.get_state()
            response = {
                "result": result,
                "state_summary": {
                    "day": state["state"]["current_day"] if state["state"] else 0,
                    "date": state["state"]["current_date"] if state["state"] else None,
                    "status": state["state"]["status"] if state["state"] else None,
                    "companies": len(state["companies"]),
                    "recent_events": len(state["recent_events"]),
                },
            }
            self._send_json(response, 200)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _check_rate_limit(self):
        ip = self.client_address[0] if self.client_address else 'unknown'
        now = time.time()
        with _rate_limit['lock']:
            if ip not in _rate_limit['attempts']:
                _rate_limit['attempts'][ip] = []
            _rate_limit['attempts'][ip] = [t for t in _rate_limit['attempts'][ip] if now - t < RATE_LIMIT_WINDOW]
            count = len(_rate_limit['attempts'][ip])
            _rate_limit['attempts'][ip].append(now)
            remaining = max(0, RATE_LIMIT_MAX - count - 1)
            self.send_header('X-RateLimit-Limit', str(RATE_LIMIT_MAX))
            self.send_header('X-RateLimit-Remaining', str(remaining))
            self.send_header('X-RateLimit-Reset', str(int(now + RATE_LIMIT_WINDOW)))
            if count >= RATE_LIMIT_MAX:
                self.send_header('Retry-After', str(RATE_LIMIT_WINDOW))
                return False
        return True

    def _add_rate_limit_headers(self):
        ip = self.client_address[0] if self.client_address else 'unknown'
        now = time.time()
        with _rate_limit['lock']:
            attempts = _rate_limit['attempts'].get(ip, [])
            remaining = max(0, RATE_LIMIT_MAX - len(attempts))
        self.send_header('X-RateLimit-Limit', str(RATE_LIMIT_MAX))
        self.send_header('X-RateLimit-Remaining', str(remaining))
        self.send_header('X-RateLimit-Reset', str(int(now + RATE_LIMIT_WINDOW)))

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        if path in ('/pxpadmin/bin/authform.cgi', '/api/login'):
            ip = self.client_address[0] if self.client_address else 'unknown'
            now = time.time()
            with _rate_limit['lock']:
                attempts = _rate_limit['attempts'].get(ip, [])
                remaining = max(0, RATE_LIMIT_MAX - len(attempts))
            self.send_header('X-RateLimit-Limit', str(RATE_LIMIT_MAX))
            self.send_header('X-RateLimit-Remaining', str(remaining))
            self.send_header('X-RateLimit-Reset', str(int(now + RATE_LIMIT_WINDOW)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _get_admin_actor(self):
        user = self._get_session_user()
        return user or 'admin'

    def _handle_admin_post(self, path):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else '{}'
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return

            actor = self._get_admin_actor()
            ip = self.client_address[0] if self.client_address else 'unknown'
            ua = self.headers.get('User-Agent', '')

            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            import admin_ops

            if path == '/api/admin/clients':
                if body.get('client_id'):
                    result = admin_ops.update_client(body['client_id'], actor, body, ip=ip, ua=ua)
                else:
                    result = admin_ops.add_client(actor, body, ip=ip, ua=ua)
            elif path == '/api/admin/financials':
                company_id = body.pop('company_id', None)
                year = int(body.pop('year', 2026))
                confidence = body.pop('confidence', 'actual')
                if not company_id:
                    self._send_json({"error": "company_id required"}, 400)
                    return
                result = admin_ops.update_company_financials(company_id, actor, year, body, confidence, ip=ip, ua=ua)
            elif path == '/api/admin/transactions':
                tx_id = body.get('transaction_id')
                amount = body.get('amount', 0)
                if not tx_id:
                    self._send_json({"error": "transaction_id required"}, 400)
                    return
                result = admin_ops.confirm_intercompany_payment(tx_id, actor, amount, ip=ip, ua=ua)
            elif path == '/api/admin/funds':
                fund_id = body.get('fund_id')
                share_class = body.get('share_class')
                nav = body.get('nav')
                if not all([fund_id, share_class, nav is not None]):
                    self._send_json({"error": "fund_id, share_class, and nav required"}, 400)
                    return
                result = admin_ops.update_fund_nav(actor, fund_id, share_class, nav, body.get('nav_date'), ip=ip, ua=ua)
            elif path == '/api/admin/events':
                result = admin_ops.add_manual_event(actor, body, ip=ip, ua=ua)
            elif path == '/api/admin/decisions':
                result = admin_ops.record_board_decision(actor, body, ip=ip, ua=ua)
            else:
                self._send_json({"error": "unknown admin endpoint"}, 404)
                return

            status = 200 if result.get('success') else 400
            self._send_json(result, status)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _serve_admin_state(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            import admin_ops
            state = admin_ops.get_admin_state()
            self._send_json(state)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _serve_admin_audit(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, 'engine'))
            import admin_ops
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            log = admin_ops.get_audit_log(
                limit=int(params.get('limit', [50])[0]),
                actor=params.get('actor', [None])[0],
                action=params.get('action', [None])[0],
                entity_type=params.get('entity_type', [None])[0],
            )
            self._send_json({"audit_log": log, "count": len(log)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _serve_console_page(self):
        sub = self._get_subdomain()
        if sub == 'panteon':
            html = PANTEON_CONSOLE_HTML
        elif sub is None:
            html = CONSOLE_HTML
        else:
            self.send_error(404)
            return
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _handle_compliance_status(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, 'centra', 'engine'))
            from compliance_report import get_compliance_status
            status = get_compliance_status()
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_compliance_report(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, 'centra', 'engine'))
            from compliance_report import load_latest_report
            report = load_latest_report()
            if report:
                self._send_json(report)
            else:
                self._send_json({"error": "no report available"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_panteon_api(self, path):
        sys.path.insert(0, os.path.join(ROOT, 'engine'))
        from data_plumbing import get_sources, get_entity_summary, get_relationship_summary, search_entities, get_entity_detail, get_entity_history, get_ingestion_stats
        from ontology import get_ontology_graph, get_business_summary, detect_risk_patterns
        from action_engine import get_rules, get_action_history, get_channels, get_rule_detail
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if path == '/api/panteon/sources' or path.startswith('/api/panteon/sources?'):
                self._send_json({"sources": get_sources()})
            elif path == '/api/panteon/entities' or path.startswith('/api/panteon/entities?'):
                company_id = params.get('company', [None])[0]
                entity_type = params.get('type', [None])[0]
                graph = get_ontology_graph(company_id=company_id, entity_type=entity_type, limit=100)
                summary = get_business_summary()
                self._send_json({"graph": graph, "summary": summary})
            elif path == '/api/panteon/entity/detail' or path.startswith('/api/panteon/entity/detail?'):
                entity_id = params.get('id', [None])[0]
                if not entity_id:
                    self._send_json({"error": "entity id required"}, 400)
                    return
                try:
                    entity_id = int(entity_id)
                except ValueError:
                    self._send_json({"error": "invalid entity id"}, 400)
                    return
                self._send_json(get_entity_detail(entity_id))
            elif path == '/api/panteon/entity/history' or path.startswith('/api/panteon/entity/history?'):
                entity_id = params.get('id', [None])[0]
                if not entity_id:
                    self._send_json({"error": "entity id required"}, 400)
                    return
                try:
                    entity_id = int(entity_id)
                except ValueError:
                    self._send_json({"error": "invalid entity id"}, 400)
                    return
                limit = int(params.get('limit', [50])[0])
                self._send_json({"history": get_entity_history(entity_id, limit)})
            elif path == '/api/panteon/stats' or path.startswith('/api/panteon/stats?'):
                self._send_json(get_ingestion_stats())
            elif path == '/api/panteon/risks' or path.startswith('/api/panteon/risks?'):
                patterns = detect_risk_patterns()
                self._send_json(patterns)
            elif path == '/api/panteon/rules' or path.startswith('/api/panteon/rules?'):
                self._send_json({"rules": get_rules()})
            elif path == '/api/panteon/rules/detail' or path.startswith('/api/panteon/rules/detail?'):
                rule_id = params.get('id', [None])[0]
                if not rule_id:
                    self._send_json({"error": "rule id required"}, 400)
                    return
                self._send_json(get_rule_detail(rule_id))
            elif path == '/api/panteon/actions' or path.startswith('/api/panteon/actions?'):
                limit = int(params.get('limit', [50])[0])
                self._send_json({"actions": get_action_history(limit)})
            elif path == '/api/panteon/relationships' or path.startswith('/api/panteon/relationships?'):
                self._send_json({"relationships": get_relationship_summary()})
            elif path == '/api/panteon/channels' or path.startswith('/api/panteon/channels?'):
                company_id = params.get('company', [None])[0]
                self._send_json({"channels": get_channels(company_id)})
            elif path == '/api/panteon/search' or path.startswith('/api/panteon/search?'):
                q = params.get('q', [None])[0]
                if not q:
                    self._send_json({"error": "query parameter 'q' required"}, 400)
                    return
                company_id = params.get('company', [None])[0]
                entity_type = params.get('type', [None])[0]
                limit = int(params.get('limit', [50])[0])
                results = search_entities(q, company_id=company_id, entity_type=entity_type, limit=limit)
                self._send_json({"results": results})
            elif path == '/api/panteon/dashboard' or path.startswith('/api/panteon/dashboard?'):
                sources = get_sources()
                entities = get_entity_summary()
                business = get_business_summary()
                patterns = detect_risk_patterns()
                rules = get_rules()
                actions = get_action_history(10)
                self._send_json({
                    "sources": sources,
                    "entity_summary": entities,
                    "business_summary": business,
                    "risk_patterns": patterns,
                    "rules": rules,
                    "recent_actions": actions,
                })
            else:
                self._send_json({"error": "unknown panteon endpoint"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_panteon_post(self, path):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length).decode('utf-8', errors='replace') if length > 0 else '{}'
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return
        except Exception:
            self._send_json({"error": "invalid request"}, 400)
            return

        sys.path.insert(0, os.path.join(ROOT, 'engine'))
        from data_plumbing import register_source, ingest_raw, ingest_batch, process_pending
        from ontology import enrich_entities, detect_cross_company_relationships, detect_risk_patterns
        from action_engine import evaluate_rules, initialize_rules, deploy_security_policy, toggle_rule, create_rule, update_rule, delete_rule, register_channel, delete_channel

        try:
            if path == '/api/panteon/ingest':
                source_id = body.get('source_id')
                company_id = body.get('company_id')
                data_type = body.get('data_type')
                records = body.get('records', [])
                if not all([source_id, company_id, data_type]):
                    if body.get('source_type') and body.get('source_name'):
                        result = register_source(company_id or 'unknown', body['source_type'], body['source_name'], body.get('config'))
                        self._send_json(result)
                        return
                    self._send_json({"error": "source_id, company_id, and data_type required"}, 400)
                    return
                if records:
                    result = ingest_batch(source_id, company_id, data_type, records)
                else:
                    result = ingest_raw(source_id, company_id, data_type, body.get('payload', {}))
                self._send_json(result)
            elif path == '/api/panteon/process':
                limit = int(body.get('limit', 100))
                result = process_pending(limit)
                self._send_json(result)
            elif path == '/api/panteon/enrich':
                enriched = enrich_entities()
                cross = detect_cross_company_relationships()
                patterns = detect_risk_patterns()
                self._send_json({"enriched": enriched, "cross_company": cross, "risk_patterns": patterns})
            elif path == '/api/panteon/evaluate':
                initialize_rules()
                patterns = detect_risk_patterns()
                result = evaluate_rules(alerts=patterns.get('alerts', []))
                self._send_json(result)
            elif path == '/api/panteon/deploy':
                policy_name = body.get('policy_name', 'security_baseline')
                targets = body.get('target_companies')
                result = deploy_security_policy(policy_name, targets)
                self._send_json(result)
            elif path == '/api/panteon/rules/toggle':
                rule_id = body.get('rule_id')
                enabled = body.get('enabled', True)
                if not rule_id:
                    self._send_json({"error": "rule_id required"}, 400)
                    return
                result = toggle_rule(rule_id, enabled)
                self._send_json(result)
            elif path == '/api/panteon/rules/create':
                rule_id = body.get('id')
                if not rule_id:
                    self._send_json({"error": "rule id required"}, 400)
                    return
                result = create_rule(rule_id, body.get('name', ''), body.get('description', ''), body.get('trigger_condition', ''), body.get('action_type', 'notify'), body.get('action_config', {}), body.get('severity', 'medium'))
                self._send_json(result)
            elif path == '/api/panteon/rules/update':
                rule_id = body.get('id')
                if not rule_id:
                    self._send_json({"error": "rule id required"}, 400)
                    return
                kwargs = {k: body[k] for k in ('name','description','trigger_condition','action_type','action_config','severity','enabled') if k in body}
                result = update_rule(rule_id, **kwargs)
                self._send_json(result)
            elif path == '/api/panteon/rules/delete':
                rule_id = body.get('id')
                if not rule_id:
                    self._send_json({"error": "rule id required"}, 400)
                    return
                result = delete_rule(rule_id)
                self._send_json(result)
            elif path == '/api/panteon/channels/register':
                channel_id = body.get('id')
                if not channel_id:
                    self._send_json({"error": "channel id required"}, 400)
                    return
                result = register_channel(channel_id, body.get('company_id', 'unknown'), body.get('channel_type', 'webhook'), body.get('webhook_url'), body.get('config'))
                self._send_json(result)
            elif path == '/api/panteon/channels/delete':
                channel_id = body.get('id')
                if not channel_id:
                    self._send_json({"error": "channel id required"}, 400)
                    return
                result = delete_channel(channel_id)
                self._send_json(result)
            else:
                self._send_json({"error": "unknown panteon endpoint"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

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


CONSOLE_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alien.Inc Console</title>
<style>
:root{--bg:#0a0a0f;--surface:#12121a;--border:#1e1e2e;--text:#e0e0e8;--muted:#888;--accent:#6c5ce7;--green:#00b894;--red:#d63031;--orange:#fdcb6e;--blue:#74b9ff}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:1.2rem;font-weight:600;color:var(--accent)}
.header .meta{color:var(--muted);font-size:.85rem}
.container{max-width:1400px;margin:0 auto;padding:2rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:1.5rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.5rem}
.card h2{font-size:1rem;font-weight:600;margin-bottom:1rem;color:var(--accent);display:flex;align-items:center;gap:.5rem}
.card h2 .badge{font-size:.7rem;background:var(--border);color:var(--muted);padding:.15rem .5rem;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:.5rem .75rem;border-bottom:1px solid var(--border);color:var(--muted);font-weight:500;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em}
td{padding:.5rem .75rem;border-bottom:1px solid var(--border)}
tr:hover{background:rgba(108,92,231,.05)}
.form-group{margin-bottom:1rem}
.form-group label{display:block;font-size:.8rem;color:var(--muted);margin-bottom:.25rem;text-transform:uppercase;letter-spacing:.05em}
.form-group input,.form-group select,.form-group textarea{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:.5rem .75rem;color:var(--text);font-size:.9rem}
.form-group textarea{min-height:80px;resize:vertical}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:var(--accent)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
.btn{background:var(--accent);color:#fff;border:none;border-radius:4px;padding:.5rem 1rem;font-size:.85rem;cursor:pointer;font-weight:500;transition:opacity .2s}
.btn:hover{opacity:.85}
.btn-danger{background:var(--red)}
.btn-sm{padding:.25rem .5rem;font-size:.75rem}
.status{display:inline-block;padding:.15rem .5rem;border-radius:3px;font-size:.75rem;font-weight:500}
.status-compliant{background:rgba(0,184,148,.15);color:var(--green)}
.status-warning{background:rgba(253,203,110,.15);color:var(--orange)}
.status-critical{background:rgba(214,48,49,.15);color:var(--red)}
.status-active{background:rgba(0,184,148,.15);color:var(--green)}
.status-closed{background:rgba(136,136,136,.15);color:var(--muted)}
.toast{position:fixed;bottom:2rem;right:2rem;background:var(--green);color:#fff;padding:.75rem 1.5rem;border-radius:6px;font-size:.9rem;opacity:0;transition:opacity .3s;pointer-events:none;z-index:100}
.toast.show{opacity:1}
.toast.error{background:var(--red)}
.tabs{display:flex;gap:.25rem;margin-bottom:1.5rem;border-bottom:1px solid var(--border)}
.tab{padding:.5rem 1rem;cursor:pointer;color:var(--muted);font-size:.85rem;border-bottom:2px solid transparent;transition:all .2s}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none}
.tab-content.active{display:block}
.risk-bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin-top:.25rem}
.risk-fill{height:100%;border-radius:3px;transition:width .3s}
.empty{color:var(--muted);font-style:italic;padding:2rem;text-align:center}
</style>
</head>
<body>
<div class="header">
<h1>Alien.Inc Console</h1>
<div class="meta">Ecosystem Operations &middot; <span id="sim-info">loading...</span></div>
</div>
<div class="container">
<div class="tabs">
<div class="tab active" onclick="showTab('overview')">Overview</div>
<div class="tab" onclick="showTab('clients')">Clients</div>
<div class="tab" onclick="showTab('financials')">Financials</div>
<div class="tab" onclick="showTab('funds')">Fund Centre</div>
<div class="tab" onclick="showTab('events')">Events</div>
<div class="tab" onclick="showTab('audit')">Audit Trail</div>
</div>
<div id="tab-overview" class="tab-content active">
<div class="grid">
<div class="card">
<h2>Risk Position <span class="badge" id="risk-score">—</span></h2>
<div id="risk-metrics"></div>
</div>
<div class="card">
<h2>Companies</h2>
<table><thead><tr><th>Company</th><th>Cash</th><th>Clients</th></tr></thead><tbody id="companies-table"></tbody></table>
</div>
<div class="card">
<h2>Debt Instruments</h2>
<table><thead><tr><th>Instrument</th><th>Principal</th><th>Rate</th><th>Status</th><th>Headroom</th></tr></thead><tbody id="debt-table"></tbody></table>
</div>
<div class="card">
<h2>Recent Audit</h2>
<div id="recent-audit"></div>
</div>
</div>
</div>
<div id="tab-clients" class="tab-content">
<div class="grid">
<div class="card" style="grid-column:1/-1">
<h2>All Clients</h2>
<table><thead><tr><th>ID</th><th>Company</th><th>Name</th><th>ACV</th><th>Status</th><th>Actions</th></tr></thead><tbody id="clients-table"></tbody></table>
</div>
<div class="card">
<h2>Add Client</h2>
<div class="form-group"><label>Company</label><select id="new-client-company"></select></div>
<div class="form-group"><label>Client Name</label><input id="new-client-name" type="text" placeholder="e.g. Northstar Group"></div>
<div class="form-row">
<div class="form-group"><label>Industry</label><input id="new-client-industry" type="text"></div>
<div class="form-group"><label>Country</label><input id="new-client-country" type="text"></div>
</div>
<div class="form-row">
<div class="form-group"><label>Annual Contract Value</label><input id="new-client-acv" type="number" value="100000"></div>
<div class="form-group"><label>Status</label><select id="new-client-status"><option>active</option><option>pipeline</option></select></div>
</div>
<button class="btn" onclick="addClient()">Add Client</button>
</div>
<div class="card">
<h2>Update Client</h2>
<div class="form-group"><label>Client ID</label><select id="update-client-id"></select></div>
<div class="form-group"><label>New Status</label><select id="update-client-status"><option value="">— no change —</option><option>active</option><option>renewal_due</option><option>paused</option><option>closed_won</option><option>closed_lost</option></select></div>
<div class="form-group"><label>New ACV</label><input id="update-client-acv" type="number" placeholder="— no change —"></div>
<button class="btn" onclick="updateClient()">Update Client</button>
</div>
</div>
</div>
<div id="tab-financials" class="tab-content">
<div class="grid">
<div class="card" style="grid-column:1/-1">
<h2>Update Company Financials</h2>
<p style="color:var(--muted);margin-bottom:1rem">Record actual quarterly/annual results for a company.</p>
<div class="form-row">
<div class="form-group"><label>Company</label><select id="fin-company"></select></div>
<div class="form-group"><label>Year</label><input id="fin-year" type="number" value="2026"></div>
</div>
<div class="form-row">
<div class="form-group"><label>Revenue</label><input id="fin-revenue" type="number"></div>
<div class="form-group"><label>Operating Costs</label><input id="fin-costs" type="number"></div>
</div>
<div class="form-row">
<div class="form-group"><label>EBITDA</label><input id="fin-ebitda" type="number"></div>
<div class="form-group"><label>Cash Ending</label><input id="fin-cash" type="number"></div>
</div>
<div class="form-group"><label>Confidence</label><select id="fin-confidence"><option value="actual">Actual</option><option value="forecast">Forecast</option></select></div>
<button class="btn" onclick="updateFinancials()">Update Financials</button>
</div>
<div class="card" style="grid-column:1/-1">
<h2>Intercompany Transactions</h2>
<table><thead><tr><th>ID</th><th>From</th><th>To</th><th>Amount</th><th>Cadence</th><th>Billed</th><th>Actions</th></tr></thead><tbody id="tx-table"></tbody></table>
</div>
</div>
</div>
<div id="tab-funds" class="tab-content">
<div class="grid">
<div class="card" style="grid-column:1/-1">
<h2>Fund Centre</h2>
<table><thead><tr><th>Fund</th><th>Share Class</th><th>ISIN</th><th>NAV (EUR)</th><th>NAV Date</th><th>AUM</th><th>Actions</th></tr></thead><tbody id="funds-table"></tbody></table>
</div>
<div class="card">
<h2>Update Fund NAV</h2>
<div class="form-group"><label>Fund</label><select id="nav-fund"></select></div>
<div class="form-group"><label>Share Class</label><select id="nav-sc"></select></div>
<div class="form-row">
<div class="form-group"><label>New NAV (EUR)</label><input id="nav-value" type="number" step="0.01"></div>
<div class="form-group"><label>NAV Date</label><input id="nav-date" type="date"></div>
</div>
<button class="btn" onclick="updateNav()">Update NAV</button>
</div>
</div>
</div>
<div id="tab-events" class="tab-content">
<div class="grid">
<div class="card">
<h2>Add Manual Event</h2>
<p style="color:var(--muted);margin-bottom:1rem">Record events that can't be automated (NDA-sensitive, strategic decisions, market intelligence).</p>
<div class="form-group"><label>Event Type</label><select id="event-type"><option value="manual_event">Manual Event</option><option value="board_decision">Board Decision</option><option value="market_intel">Market Intelligence</option><option value="client_event">Client Event</option><option value="regulatory">Regulatory Change</option><option value="geopolitical">Geopolitical Event</option></select></div>
<div class="form-group"><label>Title</label><input id="event-title" type="text" placeholder="Brief description"></div>
<div class="form-group"><label>Description</label><textarea id="event-desc" placeholder="Full details..."></textarea></div>
<div class="form-row">
<div class="form-group"><label>Severity</label><select id="event-severity"><option>low</option><option selected>medium</option><option>high</option><option>critical</option></select></div>
<div class="form-group"><label>Financial Impact</label><input id="event-impact" type="number" value="0"></div>
</div>
<div class="form-group"><label>Affected Companies (comma-separated IDs)</label><input id="event-companies" type="text" placeholder="rousseau, kmt, panteon"></div>
<button class="btn" onclick="addEvent()">Record Event</button>
</div>
<div class="card">
<h2>Record Board Decision</h2>
<div class="form-group"><label>Decision Type</label><select id="decision-type"><option value="capital_allocation">Capital Allocation</option><option value="strategy">Strategy Change</option><option value="hiring">Hiring/Departure</option><option value="acquisition">Acquisition/Divestment</option><option value="policy">Policy Change</option><option value="governance">Governance</option></select></div>
<div class="form-group"><label>Title</label><input id="decision-title" type="text" placeholder="e.g. Approve Q3 dividend distribution"></div>
<div class="form-group"><label>Description</label><textarea id="decision-desc" placeholder="Full details..."></textarea></div>
<div class="form-group"><label>Affected Companies</label><input id="decision-companies" type="text" placeholder="rousseau, kmt"></div>
<div class="form-group"><label>Financial Impact</label><input id="decision-impact" type="number" value="0"></div>
<button class="btn" onclick="addDecision()">Record Decision</button>
</div>
</div>
</div>
<div id="tab-audit" class="tab-content">
<div class="card" style="max-width:100%">
<h2>Audit Trail</h2>
<p style="color:var(--muted);margin-bottom:1rem">Every data change is logged here. This is the immutable record of who changed what and when.</p>
<table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Changes</th></tr></thead><tbody id="audit-table"></tbody></table>
</div>
</div>
</div>
<div class="toast" id="toast"></div>
<script>
let STATE = {};
function showTab(name) {
document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
document.querySelector('.tab-content#tab-' + name).classList.add('active');
event.target.classList.add('active');
}
function toast(msg, isError) {
const t = document.getElementById('toast');
t.textContent = msg;
t.className = 'toast show' + (isError ? ' error' : '');
setTimeout(() => t.className = 'toast', 3000);
}
async function api(method, path, body) {
const opts = {method, credentials: 'include', headers: {'Content-Type': 'application/json'}};
if (body) opts.body = JSON.stringify(body);
const r = await fetch(path, opts);
return r.json();
}
async function loadState() {
STATE = await api('GET', '/api/admin/state');
renderOverview();
renderClients();
renderFinancials();
renderFunds();
loadAudit();
}
function renderOverview() {
const sim = STATE.simulation_state || {};
document.getElementById('sim-info').textContent = 'Day ' + (sim.current_day || 0) + ' (' + (sim.current_date || '—') + ')';
const ct = document.getElementById('companies-table');
ct.innerHTML = (STATE.companies || []).map(c => '<tr><td>' + c.brand_name + '</td><td>$' + Number(c.current_cash || 0).toLocaleString() + '</td><td>' + (c.client_count || 0) + '</td></tr>').join('');
const dt = document.getElementById('debt-table');
dt.innerHTML = (STATE.debts || []).map(d => '<tr><td>' + d.name + '</td><td>$' + Number(d.principal_outstanding || 0).toLocaleString() + '</td><td>' + (d.interest_rate * 100).toFixed(1) + '%</td><td><span class="status status-' + (d.covenant_status || 'compliant') + '">' + (d.covenant_status || '—') + '</span></td><td>' + (d.covenant_headroom_pct != null ? d.covenant_headroom_pct.toFixed(1) + '%' : '—') + '</td></tr>').join('');
const rm = STATE.risk_metrics || {};
document.getElementById('risk-score').textContent = 'Score: ' + (rm.risk_score || 0) + '/100';
document.getElementById('risk-metrics').innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem;font-size:.85rem">' +
'<div>Covenant: <span class="status status-' + (rm.covenant_status || 'compliant') + '">' + (rm.covenant_status || '—') + '</span></div>' +
'<div>NAV Index: ' + (rm.fund_centre_nav_index || '—') + '</div>' +
'<div>Parent Runway: ' + (rm.parent_runway_months || '—') + ' mo</div>' +
'<div>Contagion: ' + (rm.contagion_count || 0) + ' below floor</div>' +
'<div>Debt Coverage: ' + (rm.debt_service_coverage_months || '—') + ' mo</div>' +
'<div>IC Exposure: ' + (rm.intercompany_to_parent_cash_pct || 0).toFixed(1) + '%</div>' +
'</div>';
const ra = document.getElementById('recent-audit');
if (STATE.recent_audit && STATE.recent_audit.length > 0) {
ra.innerHTML = '<table><tbody>' + STATE.recent_audit.slice(0, 10).map(a => '<tr><td style="white-space:nowrap">' + (a.created_at || '').substring(0, 16) + '</td><td>' + a.actor + '</td><td>' + a.action + '</td><td>' + a.entity_type + '</td></tr>').join('') + '</tbody></table>';
} else {
ra.innerHTML = '<div class="empty">No audit entries yet</div>';
}
}
function renderClients() {
const sel1 = document.getElementById('new-client-company');
const sel2 = document.getElementById('update-client-id');
sel1.innerHTML = (STATE.companies || []).map(c => '<option value="' + c.id + '">' + c.brand_name + '</option>').join('');
sel2.innerHTML = (STATE.clients || []).map(c => '<option value="' + c.id + '">' + c.id + ' — ' + c.client_name + '</option>').join('');
const ct = document.getElementById('clients-table');
ct.innerHTML = (STATE.clients || []).map(c => '<tr><td>' + c.id + '</td><td>' + c.company_id + '</td><td>' + c.client_name + '</td><td>$' + Number(c.annual_contract_value || 0).toLocaleString() + '</td><td><span class="status status-' + (c.status === 'active' ? 'active' : 'closed') + '">' + c.status + '</span></td><td><button class="btn btn-sm" onclick="document.getElementById(\\'update-client-id\\').value=\\'' + c.id + '\\';showTabDirect(\\'clients\\')">Edit</button></td></tr>').join('');
}
function showTabDirect(name) {
document.querySelectorAll('.tab').forEach((t, i) => { t.classList.toggle('active', ['overview','clients','financials','funds','events','audit'][i] === name); });
document.querySelectorAll('.tab-content').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name));
}
function renderFinancials() {
const sel = document.getElementById('fin-company');
sel.innerHTML = (STATE.companies || []).map(c => '<option value="' + c.id + '">' + c.brand_name + '</option>').join('');
const tt = document.getElementById('tx-table');
tt.innerHTML = (STATE.transactions || []).map(t => '<tr><td>' + t.id + '</td><td>' + t.from_company_id + '</td><td>' + t.to_company_id + '</td><td>$' + Number(t.amount || 0).toLocaleString() + '</td><td>' + (t.billing_cadence || '—') + '</td><td>$' + Number(t.total_billed || 0).toLocaleString() + '</td><td><button class="btn btn-sm" onclick="confirmPayment(\\'' + t.id + '\\',' + t.amount + ')">Confirm</button></td></tr>').join('');
}
function renderFunds() {
const ft = document.getElementById('funds-table');
ft.innerHTML = (STATE.funds || []).map(f => '<tr><td>' + f.name + '</td><td>' + f.share_class + '</td><td style="font-family:monospace;font-size:.8rem">' + (f.isin || '—') + '</td><td>€' + (f.nav || 0).toFixed(2) + '</td><td>' + (f.nav_date || '—') + '</td><td>' + (f.aum_formatted || '—') + '</td><td><button class="btn btn-sm" onclick="document.getElementById(\\'nav-fund\\').value=\\'' + f.id + '\\';document.getElementById(\\'nav-sc\\').value=\\'' + f.share_class + '\\'">Update</button></td></tr>').join('');
const sf = document.getElementById('nav-fund');
sf.innerHTML = [...new Set((STATE.funds || []).map(f => f.id))].map(id => '<option value="' + id + '">' + (STATE.funds.find(f => f.id === id) || {}).name + '</option>').join('');
sf.onchange = updateNavSCs;
updateNavSCs();
}
function updateNavSCs() {
const fid = document.getElementById('nav-fund').value;
const scs = (STATE.funds || []).filter(f => f.id === fid).map(f => f.share_class);
document.getElementById('nav-sc').innerHTML = scs.map(sc => '<option value="' + sc + '">' + sc + '</option>').join('');
}
async function loadAudit() {
const data = await api('GET', '/api/admin/audit');
const at = document.getElementById('audit-table');
at.innerHTML = (data.audit_log || []).map(a => {
let changes = '';
try { if (a.new_value) { const nv = JSON.parse(a.new_value); changes = Object.entries(nv).map(([k,v]) => k + '=' + v).join(', '); } } catch(e) { changes = a.new_value || ''; }
return '<tr><td style="white-space:nowrap">' + (a.created_at || '').substring(0, 16) + '</td><td>' + a.actor + '</td><td>' + a.action + '</td><td>' + a.entity_type + (a.entity_id ? '/' + a.entity_id : '') + '</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + (changes || '').replace(/"/g, '&quot;') + '">' + changes + '</td></tr>';
}).join('') || '<tr><td colspan="5" class="empty">No audit entries</td></tr>';
}
async function addClient() {
const body = {
company_id: document.getElementById('new-client-company').value,
client_name: document.getElementById('new-client-name').value,
industry: document.getElementById('new-client-industry').value,
country: document.getElementById('new-client-country').value,
annual_contract_value: Number(document.getElementById('new-client-acv').value),
status: document.getElementById('new-client-status').value
};
const r = await api('POST', '/api/admin/clients', body);
if (r.success) { toast('Client added: ' + r.client_id); loadState(); } else { toast(r.error || 'Failed', true); }
}
async function updateClient() {
const clientId = document.getElementById('update-client-id').value;
const updates = {client_id: clientId};
const status = document.getElementById('update-client-status').value;
const acv = document.getElementById('update-client-acv').value;
if (status) updates.status = status;
if (acv) updates.annual_contract_value = Number(acv);
const r = await api('POST', '/api/admin/clients', updates);
if (r.success) { toast('Client updated'); loadState(); } else { toast(r.error || 'Failed', true); }
}
async function updateFinancials() {
const body = {
company_id: document.getElementById('fin-company').value,
year: Number(document.getElementById('fin-year').value),
confidence: document.getElementById('fin-confidence').value
};
const rev = document.getElementById('fin-revenue').value;
const costs = document.getElementById('fin-costs').value;
const ebitda = document.getElementById('fin-ebitda').value;
const cash = document.getElementById('fin-cash').value;
if (rev) body.revenue = Number(rev);
if (costs) body.operating_costs = Number(costs);
if (ebitda) body.ebitda = Number(ebitda);
if (cash) body.cash_ending = Number(cash);
const r = await api('POST', '/api/admin/financials', body);
if (r.success) { toast('Financials updated'); loadState(); } else { toast(r.error || 'Failed', true); }
}
async function confirmPayment(txId, amount) {
if (!confirm('Confirm payment of $' + amount.toLocaleString() + ' for ' + txId + '?')) return;
const r = await api('POST', '/api/admin/transactions', {transaction_id: txId, amount: amount});
if (r.success) { toast('Payment confirmed'); loadState(); } else { toast(r.error || 'Failed', true); }
}
async function updateNav() {
const body = {
fund_id: document.getElementById('nav-fund').value,
share_class: document.getElementById('nav-sc').value,
nav: Number(document.getElementById('nav-value').value),
nav_date: document.getElementById('nav-date').value || undefined
};
const r = await api('POST', '/api/admin/funds', body);
if (r.success) { toast('NAV updated to €' + body.nav); loadState(); } else { toast(r.error || 'Failed', true); }
}
async function addEvent() {
const companies = document.getElementById('event-companies').value.split(',').map(s => s.trim()).filter(Boolean);
const body = {
event_type: document.getElementById('event-type').value,
title: document.getElementById('event-title').value,
description: document.getElementById('event-desc').value,
impact_severity: document.getElementById('event-severity').value,
financial_impact: Number(document.getElementById('event-impact').value),
affected_company_ids: companies
};
const r = await api('POST', '/api/admin/events', body);
if (r.success) { toast('Event recorded: #' + r.event_id); loadState(); loadAudit(); } else { toast(r.error || 'Failed', true); }
}
async function addDecision() {
const companies = document.getElementById('decision-companies').value.split(',').map(s => s.trim()).filter(Boolean);
const body = {
decision_type: document.getElementById('decision-type').value,
title: document.getElementById('decision-title').value,
description: document.getElementById('decision-desc').value,
financial_impact: Number(document.getElementById('decision-impact').value),
affected_company_ids: companies
};
const r = await api('POST', '/api/admin/decisions', body);
if (r.success) { toast('Decision recorded: #' + r.decision_id); loadState(); loadAudit(); } else { toast(r.error || 'Failed', true); }
}
document.getElementById('nav-date').valueAsDate = new Date();
loadState();
setInterval(loadState, 30000);
setInterval(loadAudit, 15000);
</script>
 </body>
 </html>'''


PANTEON_CONSOLE_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Panteon — Intelligence Platform</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
:root{--bg:#0b0d12;--surface:#11141b;--border:#1c2030;--text:#d0d4e0;--muted:#6b7280;--accent:#3b82f6;--green:#10b981;--red:#ef4444;--orange:#f59e0b;--purple:#8b5cf6}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:.75rem 1.5rem;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:1.1rem;font-weight:600;color:var(--accent);display:flex;align-items:center;gap:.5rem}
.header h1 .logo{width:20px;height:20px;background:var(--accent);border-radius:3px;display:inline-block}
.header .meta{color:var(--muted);font-size:.8rem}
.container{max-width:1400px;margin:0 auto;padding:1.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:1.25rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.25rem}
.card h2{font-size:.9rem;font-weight:600;margin-bottom:.75rem;color:var(--accent);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--border);color:var(--muted);font-weight:500;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em}
td{padding:.4rem .6rem;border-bottom:1px solid rgba(28,32,48,.5)}
tr:hover{background:rgba(59,130,246,.04)}
.badge{display:inline-block;padding:.1rem .45rem;border-radius:3px;font-size:.7rem;font-weight:600;text-transform:uppercase}
.badge-critical{background:rgba(239,68,68,.15);color:var(--red)}
.badge-high{background:rgba(245,158,11,.15);color:var(--orange)}
.badge-medium{background:rgba(139,92,246,.15);color:var(--purple)}
.badge-low{background:rgba(107,114,128,.15);color:var(--muted)}
.badge-active{background:rgba(16,185,129,.15);color:var(--green)}
.badge-enabled{background:rgba(16,185,129,.15);color:var(--green)}
.badge-disabled{background:rgba(107,114,128,.15);color:var(--muted)}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}
.stat{background:rgba(59,130,246,.05);border:1px solid rgba(59,130,246,.1);border-radius:6px;padding:.75rem}
.stat .label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.stat .value{font-size:1.3rem;font-weight:700;margin-top:.2rem}
.tabs{display:flex;gap:.25rem;margin-bottom:1.25rem;border-bottom:1px solid var(--border);flex-wrap:wrap}
.tab{padding:.4rem .75rem;cursor:pointer;color:var(--muted);font-size:.8rem;border-bottom:2px solid transparent;transition:all .2s}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none}
.tab-content.active{display:block}
.btn{background:var(--accent);color:#fff;border:none;border-radius:4px;padding:.4rem .75rem;font-size:.8rem;cursor:pointer;font-weight:500}
.btn:hover{opacity:.85}
.btn-sm{padding:.2rem .4rem;font-size:.7rem}
.btn-green{background:var(--green)}
.btn-danger{background:var(--red)}
.btn-outline{background:transparent;border:1px solid var(--border);color:var(--text)}
.toast{position:fixed;bottom:1.5rem;right:1.5rem;background:var(--green);color:#fff;padding:.6rem 1.25rem;border-radius:6px;font-size:.85rem;opacity:0;transition:opacity .3s;z-index:100}
.toast.show{opacity:1}
.toast.error{background:var(--red)}
.empty{color:var(--muted);font-style:italic;padding:1.5rem;text-align:center;font-size:.85rem}
.risk-bar{height:4px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:.3rem}
.risk-fill{height:100%;border-radius:2px;transition:width .3s}
.graph-container{width:100%;height:500px;background:rgba(0,0,0,.3);border-radius:6px;overflow:hidden}
.graph-container svg{width:100%;height:100%}
.modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:center;justify-content:center}
.modal-overlay.show{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.5rem;max-width:700px;width:90%;max-height:80vh;overflow-y:auto}
.modal h2{margin-bottom:1rem;color:var(--accent)}
.modal-close{float:right;cursor:pointer;color:var(--muted);font-size:1.2rem}
.modal-close:hover{color:var(--text)}
.form-group{margin-bottom:.75rem}
.form-group label{display:block;font-size:.75rem;color:var(--muted);margin-bottom:.25rem;text-transform:uppercase;letter-spacing:.05em}
.form-group input,.form-group select,.form-group textarea{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.4rem;border-radius:3px;font-size:.8rem;font-family:inherit}
.form-group textarea{font-family:monospace;font-size:.75rem}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
.graph-legend{display:flex;gap:1rem;flex-wrap:wrap;padding:.5rem 0;font-size:.75rem;color:var(--muted)}
.graph-legend span{display:flex;align-items:center;gap:.25rem}
.graph-legend .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
</style>
</head>
<body>
<div class="header">
<h1><span class="logo"></span> Panteon Intelligence Platform</h1>
<div class="meta">Group Security & Operations &middot; <span id="status">loading...</span></div>
</div>
<div class="container">
<div class="tabs">
<div class="tab active" onclick="showTab('overview')">Overview</div>
<div class="tab" onclick="showTab('sources')">Data Sources</div>
<div class="tab" onclick="showTab('pipeline')">Pipeline</div>
<div class="tab" onclick="showTab('ontology')">Ontology</div>
<div class="tab" onclick="showTab('graph')">Graph</div>
<div class="tab" onclick="showTab('risks')">Risk Patterns</div>
<div class="tab" onclick="showTab('rules')">Action Rules</div>
<div class="tab" onclick="showTab('builder')">Rule Builder</div>
<div class="tab" onclick="showTab('channels')">Channels</div>
<div class="tab" onclick="showTab('actions')">Action Log</div>
<div class="tab" onclick="showTab('ingest')">Ingest Data</div>
</div>

<div id="tab-overview" class="tab-content active">
<div class="grid">
<div class="card"><h2>Platform Status</h2><div class="stat-grid" id="overview-stats"></div></div>
<div class="card"><h2>Active Risk Patterns</h2><div id="overview-risks"></div></div>
<div class="card"><h2>Recent Actions</h2><div id="overview-actions"></div></div>
<div class="card"><h2>Entity Categories</h2><div id="overview-categories"></div></div>
</div>
</div>

<div id="tab-sources" class="tab-content">
<div class="card" style="max-width:100%">
<h2>Registered Data Sources</h2>
<table><thead><tr><th>Source ID</th><th>Company</th><th>Type</th><th>Name</th><th>Status</th><th>Records</th><th>Last Ingested</th></tr></thead><tbody id="sources-table"></tbody></table>
</div>
</div>

<div id="tab-pipeline" class="tab-content">
<div class="grid">
<div class="card"><h2>Ingestion Pipeline</h2><div class="stat-grid" id="pipeline-stats"></div></div>
<div class="card"><h2>By Data Type</h2><div id="pipeline-by-type"></div></div>
<div class="card" style="grid-column:1/-1"><h2>Recent Ingestions</h2><div id="pipeline-recent"></div></div>
</div>
</div>

<div id="tab-ontology" class="tab-content">
<div class="grid">
<div class="card" style="grid-column:1/-1"><h2>Entity Summary</h2><table><thead><tr><th>Entity Type</th><th>Count</th><th>Companies</th></tr></thead><tbody id="entity-table"></tbody></table></div>
<div class="card" style="grid-column:1/-1"><h2>Top Risk Entities</h2><table><thead><tr><th>Name</th><th>Type</th><th>Company</th><th>Risk Score</th><th>Category</th></tr></thead><tbody id="risk-entity-table"></tbody></table></div>
</div>
</div>

<div id="tab-graph" class="tab-content">
<div class="card" style="max-width:100%">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
<h2 style="margin:0">Entity Graph</h2>
<div style="display:flex;gap:.5rem;align-items:center">
<select id="graph-company-filter" onchange="renderGraph()" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.2rem .4rem;border-radius:3px;font-size:.75rem"><option value="">All Companies</option></select>
<select id="graph-type-filter" onchange="renderGraph()" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.2rem .4rem;border-radius:3px;font-size:.75rem"><option value="">All Types</option></select>
</div>
</div>
<div class="graph-legend">
<span><span class="dot" style="background:var(--accent)"></span> Entity</span>
<span><span class="dot" style="background:var(--green)"></span> Human</span>
<span><span class="dot" style="background:var(--orange)"></span> Infrastructure</span>
<span><span class="dot" style="background:var(--red)"></span> Security</span>
<span><span class="dot" style="background:var(--purple)"></span> Financial</span>
<span style="color:var(--muted)">Drag to pan &middot; Scroll to zoom</span>
</div>
<div class="graph-container" id="graph-container"></div>
</div>
</div>

<div id="tab-risks" class="tab-content">
<div class="card" style="max-width:100%">
<h2>Detected Risk Patterns</h2>
<div id="risk-patterns"></div>
<button class="btn" style="margin-top:1rem" onclick="runOntology()">Re-scan Ontology</button>
<button class="btn" style="margin-top:1rem;margin-left:.5rem" onclick="runEvaluate()">Evaluate Rules</button>
</div>
</div>

<div id="tab-rules" class="tab-content">
<div class="card" style="max-width:100%">
<h2>Action Rules (AIP)</h2>
<table><thead><tr><th>Name</th><th>Type</th><th>Severity</th><th>Enabled</th><th>Executions</th><th>Last Run</th></tr></thead><tbody id="rules-table"></tbody></table>
</div>
</div>

<div id="tab-builder" class="tab-content">
<div class="grid">
<div class="card">
<h2>Create Rule</h2>
<div class="form-group"><label>Rule ID</label><input id="rule-id" placeholder="e.g. panteon-my-custom-rule"></div>
<div class="form-group"><label>Name</label><input id="rule-name" placeholder="e.g. Critical Port Scan Detection"></div>
<div class="form-group"><label>Description</label><input id="rule-desc" placeholder="Describe when this rule triggers"></div>
<div class="form-group"><label>Trigger Condition</label><input id="rule-condition" placeholder="e.g. ontology_entities.entity_type = 'security_alert' AND ontology_entities.risk_score >= 30"></div>
<div class="form-row">
<div class="form-group"><label>Action Type</label><select id="rule-action"><option>notify</option><option>escalate</option><option>notify_and_escalate</option><option>deploy_policy</option></select></div>
<div class="form-group"><label>Severity</label><select id="rule-severity"><option>medium</option><option>high</option><option>critical</option></select></div>
</div>
<div class="form-group"><label>Action Config (JSON)</label><textarea id="rule-config" rows="4" placeholder="{&quot;notify&quot;: [&quot;panteon&quot;], &quot;message_template&quot;: &quot;Alert at {company_id}: {entity_name}&quot;}"></textarea></div>
<button class="btn" onclick="createRule()">Create Rule</button>
</div>
<div class="card">
<h2>Existing Rules</h2>
<div id="builder-rules-list"></div>
</div>
</div>
</div>

<div id="tab-channels" class="tab-content">
<div class="grid">
<div class="card">
<h2>Register Notification Channel</h2>
<div class="form-group"><label>Channel ID</label><input id="chan-id" placeholder="e.g. panteon-slack-soc"></div>
<div class="form-group"><label>Company</label><select id="chan-company" style="width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px"><option>panteon</option><option>kmt</option><option>rousseau</option><option>immanuel</option><option>sp</option><option>tdac</option><option>alcantara</option></select></div>
<div class="form-row">
<div class="form-group"><label>Type</label><select id="chan-type"><option>webhook</option><option>slack</option><option>pagerduty</option><option>email</option></select></div>
<div class="form-group"><label>Webhook URL</label><input id="chan-url" placeholder="https://hooks.slack.com/..."></div>
</div>
<button class="btn" onclick="registerChannel()">Register Channel</button>
</div>
<div class="card"><h2>Configured Channels</h2><div id="channels-list"></div></div>
</div>
</div>

<div id="tab-actions" class="tab-content">
<div class="card" style="max-width:100%">
<h2>Action Execution Log</h2>
<table><thead><tr><th>Time</th><th>Rule</th><th>Action</th><th>Targets</th><th>Status</th></tr></thead><tbody id="actions-table"></tbody></table>
</div>
</div>

<div id="tab-ingest" class="tab-content">
<div class="grid">
<div class="card">
<h2>Register New Source</h2>
<div class="stat" style="margin-bottom:1rem;background:rgba(59,130,246,.03)"><span class="label">Data Types Available</span><div style="margin-top:.3rem;font-size:.8rem;color:var(--text)">aws_bill, github_commit, jira_ticket, financial_sheet, security_alert, network_log, hr_record, client_interaction</div></div>
<div class="stat" style="margin-bottom:1rem"><label class="label">Company</label><select id="reg-company" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px"><option>panteon</option><option>kmt</option><option>rousseau</option><option>immanuel</option><option>centra</option><option>tdac</option><option>alcantaraartfoundation</option></select></div>
<div class="stat" style="margin-bottom:1rem"><label class="label">Source Type</label><select id="reg-type" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px"><option>security_alert</option><option>github_commit</option><option>jira_ticket</option><option>financial_sheet</option><option>aws_bill</option><option>network_log</option><option>hr_record</option><option>client_interaction</option></select></div>
<div class="stat" style="margin-bottom:1rem"><label class="label">Source Name</label><input id="reg-name" type="text" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px" placeholder="e.g. Production SOC Feed"></div>
<button class="btn" onclick="registerSource()">Register Source</button>
</div>
<div class="card">
<h2>Ingest Raw Data</h2>
<div class="stat" style="margin-bottom:1rem"><label class="label">Source ID</label><input id="ingest-source" type="text" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px" placeholder="e.g. panteon-security_alert-production-soc-feed"></div>
<div class="stat" style="margin-bottom:1rem"><label class="label">Data Type</label><select id="ingest-type" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px"><option>security_alert</option><option>github_commit</option><option>jira_ticket</option><option>financial_sheet</option><option>aws_bill</option><option>network_log</option><option>hr_record</option><option>client_interaction</option></select></div>
<div class="stat" style="margin-bottom:1rem"><label class="label">JSON Payload</label><textarea id="ingest-payload" rows="6" style="width:100%;margin-top:.3rem;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.3rem;border-radius:3px;font-family:monospace;font-size:.75rem" placeholder='{"type":"intrusion_attempt","severity":"critical","host":"srv-01"}'></textarea></div>
<button class="btn" onclick="ingestData()">Ingest</button>
<button class="btn" style="margin-left:.5rem;background:var(--purple)" onclick="processAll()">Process Pending</button>
</div>
</div>
</div>
</div>

<div class="modal-overlay" id="entity-modal">
<div class="modal">
<span class="modal-close" onclick="closeModal()">&times;</span>
<h2 id="modal-title">Entity Detail</h2>
<div id="modal-body"></div>
</div>
</div>

<div class="toast" id="toast"></div>

<script>
const TAB_NAMES=['overview','sources','pipeline','ontology','graph','risks','rules','builder','channels','actions','ingest'];
function showTab(name){document.querySelectorAll('.tab').forEach((t,i)=>{t.classList.toggle('active',TAB_NAMES[i]===name)});document.querySelectorAll('.tab-content').forEach(t=>t.classList.toggle('active',t.id==='tab-'+name))}
function toast(msg,err){const t=document.getElementById('toast');t.textContent=msg;t.className='toast show'+(err?' error':'');setTimeout(()=>t.className='toast',3000)}
async function api(method,path,body){const opts={method,credentials:'include',headers:{'Content-Type':'application/json'}};if(body)opts.body=JSON.stringify(body);const r=await fetch(path,opts);return r.json()}

function openModal(title,html){document.getElementById('modal-title').textContent=title;document.getElementById('modal-body').innerHTML=html;document.getElementById('entity-modal').classList.add('show')}
function closeModal(){document.getElementById('entity-modal').classList.remove('show')}
document.getElementById('entity-modal').addEventListener('click',function(e){if(e.target===this)closeModal()});

async function loadDashboard(){
  const d=await api('GET','/api/panteon/dashboard');
  renderOverview(d);
  renderSources(d.sources);
  renderEntitySummary(d.entity_summary);
  renderRiskPatterns(d.risk_patterns);
  renderRules(d.rules);
  renderActions(d.recent_actions);
  renderBusinessSummary(d.business_summary);
  const ec=d.entity_summary?d.entity_summary.reduce((s,e)=>s+e.count,0):0;
  document.getElementById('status').textContent=(d.sources?d.sources.length:0)+' sources &middot; '+ec+' entities';
}
function renderOverview(d){
  const s=document.getElementById('overview-stats');
  const ec=d.entity_summary?d.entity_summary.reduce((a,e)=>a+e.count,0):0;
  const rc=d.risk_patterns?d.risk_patterns.patterns_detected:0;
  const ac=d.recent_actions?d.recent_actions.length:0;
  const ruc=d.rules?d.rules.length:0;
  s.innerHTML='<div class="stat"><div class="label">Data Sources</div><div class="value">'+(d.sources?d.sources.length:0)+'</div></div><div class="stat"><div class="label">Entities Mapped</div><div class="value">'+ec+'</div></div><div class="stat"><div class="label">Risk Patterns</div><div class="value" style="color:'+(rc>0?'var(--orange)':'var(--green)')+'">'+rc+'</div></div><div class="stat"><div class="label">Action Rules</div><div class="value">'+ruc+'</div></div>';
  const rp=d.risk_patterns?d.risk_patterns.alerts||[]:[];
  const rdiv=document.getElementById('overview-risks');
  rdiv.innerHTML=rp.length?rp.slice(0,5).map(a=>'<div style="margin-bottom:.5rem"><span class="badge badge-'+a.severity+'">'+a.severity+'</span> <strong>'+a.company_id+'</strong>: '+a.description.substring(0,70)+'</div>').join(''):'<div class="empty">No risk patterns detected</div>';
  const acts=d.recent_actions||[];
  const adiv=document.getElementById('overview-actions');
  adiv.innerHTML=acts.length?'<table><tbody>'+acts.slice(0,5).map(a=>'<tr><td style="white-space:nowrap">'+(a.executed_at||'').substring(0,16)+'</td><td>'+a.rule_name+'</td><td><span class="badge badge-active">'+a.status+'</span></td></tr>').join('')+'</tbody></table>':'<div class="empty">No actions executed yet</div>';
  const cats=d.business_summary?d.business_summary.categories||[]:[];
  const cdiv=document.getElementById('overview-categories');
  cdiv.innerHTML=cats.length?cats.slice(0,6).map(c=>'<div style="margin-bottom:.4rem"><span style="color:var(--muted)">'+c.category+'</span>: <strong>'+c.count+'</strong> entities, risk '+(c.avg_risk||0).toFixed(1)+'</div>').join(''):'<div class="empty">No categories</div>';
}
function renderSources(sources){
  const t=document.getElementById('sources-table');
  t.innerHTML=(sources||[]).map(s=>'<tr><td style="font-family:monospace;font-size:.75rem">'+s.id+'</td><td>'+s.company_id+'</td><td>'+s.source_type+'</td><td>'+s.source_name+'</td><td><span class="badge badge-'+s.status+'">'+s.status+'</span></td><td>'+(s.records_ingested||0)+'</td><td style="white-space:nowrap">'+(s.last_ingested_at||'never').substring(0,16)+'</td></tr>').join('')||'<tr><td colspan="7" class="empty">No data sources registered</td></tr>';
}
function renderEntitySummary(entities){
  const t=document.getElementById('entity-table');
  t.innerHTML=(entities||[]).map(e=>'<tr><td>'+e.entity_type+'</td><td>'+e.count+'</td><td>'+e.companies+'</td></tr>').join('')||'<tr><td colspan="3" class="empty">No entities</td></tr>';
}
function renderRiskPatterns(data){
  const div=document.getElementById('risk-patterns');
  const alerts=(data&&data.alerts)||[];
  div.innerHTML=alerts.length?alerts.map(a=>'<div style="margin-bottom:.5rem;padding:.5rem;background:rgba(239,68,68,.05);border-radius:4px;border-left:3px solid '+(a.severity==='critical'?'var(--red)':a.severity==='high'?'var(--orange)':'var(--purple)')+'"><span class="badge badge-'+a.severity+'">'+a.severity+'</span> <strong>'+a.company_id+'</strong>: '+a.description+'</div>').join(''):'<div class="empty">No risk patterns detected</div>';
}
function renderRules(rules){
  const t=document.getElementById('rules-table');
  t.innerHTML=(rules||[]).map(r=>'<tr><td>'+r.name+'</td><td>'+r.action_type+'</td><td><span class="badge badge-'+r.severity+'">'+r.severity+'</span></td><td><span class="badge badge-'+(r.enabled?'enabled':'disabled')+'">'+(r.enabled?'enabled':'disabled')+'</span></td><td>'+(r.execution_count||0)+'</td><td style="white-space:nowrap">'+(r.last_executed||'never').substring(0,16)+'</td></tr>').join('')||'<tr><td colspan="6" class="empty">No rules</td></tr>';
}
function renderActions(actions){
  const t=document.getElementById('actions-table');
  t.innerHTML=(actions||[]).map(a=>'<tr><td style="white-space:nowrap">'+(a.executed_at||'').substring(0,16)+'</td><td>'+a.rule_name+'</td><td>'+a.action_taken+'</td><td>'+(a.target_company_ids||'').substring(0,40)+'</td><td><span class="badge badge-active">'+a.status+'</span></td></tr>').join('')||'<tr><td colspan="5" class="empty">No actions executed</td></tr>';
}
function renderBusinessSummary(s){
  if(!s||!s.top_risk_entities)return;
  const t=document.getElementById('risk-entity-table');
  t.innerHTML=(s.top_risk_entities||[]).map(e=>{const p=e.properties?JSON.parse(e.properties):{};return '<tr onclick="showEntityDetail('+e.id+')" style="cursor:pointer"><td>'+e.entity_name+'</td><td>'+e.entity_type+'</td><td>'+e.company_id+'</td><td><div style="display:flex;align-items:center;gap:.5rem"><span>'+Math.round(e.risk_score||0)+'</span><div class="risk-bar" style="width:60px"><div class="risk-fill" style="width:'+Math.min(100,e.risk_score||0)+'%;background:'+(e.risk_score>=40?'var(--red)':e.risk_score>=20?'var(--orange)':'var(--accent)')+'"></div></div></div></td><td>'+(p.category||p.business_context||'')+'</td></tr>'}).join('')||'<tr><td colspan="5" class="empty">No risky entities</td></tr>';
}

// ── Entity Detail Modal ───────────────────────────────────
async function showEntityDetail(id){
  const d=await api('GET','/api/panteon/entity/detail?id='+id);
  if(d.error){toast(d.error,true);return}
  const e=d.entity;
  const p=e.properties?JSON.parse(e.properties):{};
  const props=Object.entries(p).map(([k,v])=>'<tr><td style="color:var(--muted)">'+k+'</td><td>'+JSON.stringify(v)+'</td></tr>').join('');
  const rout=(d.relationships_out||[]).slice(0,10).map(r=>'<tr><td>'+r.relationship_type+'</td><td><a onclick="showEntityDetail('+r.to_entity_id+')" style="color:var(--accent);cursor:pointer">'+r.to_name+'</a> <span style="color:var(--muted)">('+r.to_type+')</span></td></tr>').join('');
  const rin=(d.relationships_in||[]).slice(0,10).map(r=>'<tr><td>'+r.relationship_type+'</td><td><a onclick="showEntityDetail('+r.from_entity_id+')" style="color:var(--accent);cursor:pointer">'+r.from_name+'</a> <span style="color:var(--muted)">('+r.from_type+')</span></td></tr>').join('');
  const hist=(d.recent_history||[]).slice(0,5).map(h=>'<tr><td style="white-space:nowrap">'+(h.changed_at||'').substring(0,16)+'</td><td>'+(h.change_reason||'')+'</td><td>risk: '+Math.round(h.risk_score||0)+'</td></tr>').join('');
  const html='<div style="margin-bottom:1rem"><span class="badge badge-'+e.entity_type+'">'+e.entity_type+'</span> <strong>'+e.entity_name+'</strong> <span style="color:var(--muted)">at '+e.company_id+'</span></div>'+
    '<div style="margin-bottom:1rem"><span class="label" style="color:var(--muted);font-size:.75rem;text-transform:uppercase">Risk Score</span><div style="display:flex;align-items:center;gap:.5rem;margin-top:.25rem"><span style="font-size:1.5rem;font-weight:700">'+Math.round(e.risk_score||0)+'</span><div class="risk-bar" style="width:100px"><div class="risk-fill" style="width:'+Math.min(100,e.risk_score||0)+'%;background:'+(e.risk_score>=40?'var(--red)':e.risk_score>=20?'var(--orange)':'var(--accent)')+'"></div></div></div></div>'+
    (props?'<h3 style="font-size:.8rem;margin-bottom:.5rem;color:var(--muted)">Properties</h3><table><tbody>'+props+'</tbody></table>':'')+
    (rout?'<h3 style="font-size:.8rem;margin:.5rem 0;color:var(--muted)">Outgoing Relationships</h3><table><thead><tr><th>Type</th><th>Target</th></tr></thead><tbody>'+rout+'</tbody></table>':'')+
    (rin?'<h3 style="font-size:.8rem;margin:.5rem 0;color:var(--muted)">Incoming Relationships</h3><table><thead><tr><th>Type</th><th>Source</th></tr></thead><tbody>'+rin+'</tbody></table>':'')+
    (hist?'<h3 style="font-size:.8rem;margin:.5rem 0;color:var(--muted)">Recent History</h3><table><thead><tr><th>Time</th><th>Reason</th><th>Score</th></tr></thead><tbody>'+hist+'</tbody></table>':'');
  openModal('Entity Detail: '+e.entity_name,html);
}

// ── Pipeline Observability ─────────────────────────────────
async function loadPipelineStats(){
  const d=await api('GET','/api/panteon/stats');
  const s=document.getElementById('pipeline-stats');
  s.innerHTML='<div class="stat"><div class="label">Total Raw Records</div><div class="value">'+d.total_raw_records+'</div></div><div class="stat"><div class="label">Pending Processing</div><div class="value" style="color:'+(d.pending_processing>0?'var(--orange)':'var(--green)')+'">'+d.pending_processing+'</div></div><div class="stat"><div class="label">Processed</div><div class="value">'+d.processed+'</div></div><div class="stat"><div class="label">Total Sources</div><div class="value">'+d.total_sources+'</div></div><div class="stat"><div class="label">Total Entities</div><div class="value">'+d.total_entities+'</div></div><div class="stat"><div class="label">Total Relationships</div><div class="value">'+d.total_relationships+'</div></div>';
  const bt=document.getElementById('pipeline-by-type');
  bt.innerHTML='<table><thead><tr><th>Data Type</th><th>Count</th></tr></thead><tbody>'+(d.by_data_type||[]).map(t=>'<tr><td>'+t.data_type+'</td><td>'+t.count+'</td></tr>').join('')+'</tbody></table>';
  const rec=document.getElementById('pipeline-recent');
  rec.innerHTML='<table><thead><tr><th>Time</th><th>Type</th><th>Company</th></tr></thead><tbody>'+(d.recent_ingestions||[]).map(r=>'<tr><td style="white-space:nowrap">'+(r.ingested_at||'').substring(0,16)+'</td><td>'+r.data_type+'</td><td>'+r.company_id+'</td></tr>').join('')+'</tbody></table>';
}

// ── D3 Graph ──────────────────────────────────────────────
let graphData=null;
async function loadGraph(){
  const qs=[]; const cf=document.getElementById('graph-company-filter').value; const tf=document.getElementById('graph-type-filter').value;
  if(cf)qs.push('company='+cf); if(tf)qs.push('type='+tf);
  const d=await api('GET','/api/panteon/entities?'+qs.join('&'));
  graphData=d;
  // Populate filter dropdowns
  if(d.summary&&d.summary.categories){
    const cfEl=document.getElementById('graph-company-filter');
    if(cfEl.options.length<=1&&d.summary.categories[0]&&d.summary.categories[0].companies){
      const comps=[...new Set(d.summary.categories.flatMap(c=>(c.companies||'').split(',')))].filter(Boolean);
      comps.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;cfEl.appendChild(o)});
    }
  }
  if(d.graph&&d.graph.entities){
    const tfEl=document.getElementById('graph-type-filter');
    if(tfEl.options.length<=1){
      const types=[...new Set(d.graph.entities.map(e=>e.entity_type))].sort();
      types.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;tfEl.appendChild(o)});
    }
  }
  renderGraph();
}
function colorForType(t){
  const map={team_member:'var(--green)',developer:'var(--green)',person:'var(--green)',
    server:'var(--orange)',cloud_service:'var(--orange)',network_address:'var(--orange)',running_process:'var(--orange)',
    security_alert:'var(--red)',system_user:'var(--red)',
    financial_metric:'var(--purple)',financial_account:'var(--purple)',expense_category:'var(--purple)',
    cloud_account:'var(--accent)',code_repository:'var(--accent)',code_asset:'var(--accent)',
    work_item:'var(--accent)',project:'var(--accent)',business_client:'var(--accent)'};
  return map[t]||'var(--muted)';
}
function renderGraph(){
  if(!graphData||!graphData.graph)return;
  const entities=graphData.graph.entities||[];
  const relationships=graphData.graph.relationships||[];
  if(!entities.length){document.getElementById('graph-container').innerHTML='<div class="empty">No entities to display</div>';return}
  const container=document.getElementById('graph-container');
  const w=container.clientWidth||900,h=500;
  container.innerHTML='';

  const svg=d3.select(container).append('svg').attr('width',w).attr('height',h);
  const g=svg.append('g');
  const zoom=d3.zoom().scaleExtent([.1,4]).on('zoom',(event)=>g.attr('transform',event.transform));
  svg.call(zoom);

  const nodeMap={};
  entities.forEach(e=>{nodeMap[e.id]=e});
  const links=relationships.map(r=>({source:r.from_entity_id,target:r.to_entity_id,type:r.relationship_type})).filter(l=>nodeMap[l.source]&&nodeMap[l.target]);

  const simulation=d3.forceSimulation(entities)
    .force('link',d3.forceLink(links).id(d=>d.id).distance(80))
    .force('charge',d3.forceManyBody().strength(-150))
    .force('center',d3.forceCenter(w/2,h/2))
    .force('collision',d3.forceCollide(20));

  const link=g.selectAll('line').data(links).join('line')
    .attr('stroke','var(--border)').attr('stroke-width',.5).attr('stroke-opacity',.4);

  const node=g.selectAll('g.node').data(entities).join('g').attr('class','node')
    .call(d3.drag().on('start',(event,d)=>{if(!event.active)simulation.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y})
      .on('drag',(event,d)=>{d.fx=event.x;d.fy=event.y})
      .on('end',(event,d)=>{if(!event.active)simulation.alphaTarget(0);d.fx=null;d.fy=null}));

  node.append('circle').attr('r',6).attr('fill',d=>colorForType(d.entity_type)).attr('stroke','var(--bg)').attr('stroke-width',1.5);
  node.append('title').text(d=>d.entity_name+' ('+d.entity_type+', '+d.company_id+')');

  node.on('click',(event,d)=>{event.stopPropagation();showEntityDetail(d.id)});

  simulation.on('tick',()=>{
    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
    node.attr('transform',d=>'translate('+d.x+','+d.y+')');
  });
}

// ── Rule Builder ───────────────────────────────────────────
async function loadBuilderRules(){
  const d=await api('GET','/api/panteon/rules');
  const div=document.getElementById('builder-rules-list');
  div.innerHTML='<table><thead><tr><th>ID</th><th>Name</th><th>Severity</th><th>Enabled</th><th>Actions</th></tr></thead><tbody>'+
    (d.rules||[]).map(r=>'<tr><td style="font-family:monospace;font-size:.75rem">'+r.id+'</td><td>'+r.name+'</td><td><span class="badge badge-'+r.severity+'">'+r.severity+'</span></td><td><span class="badge badge-'+(r.enabled?'enabled':'disabled')+'">'+(r.enabled?'enabled':'disabled')+'</span></td><td>'+
    '<button class="btn btn-sm" onclick="toggleRule(\''+r.id+'\','+(!r.enabled)+')" style="margin-right:.25rem">'+(r.enabled?'Disable':'Enable')+'</button>'+
    '<button class="btn btn-sm btn-danger" onclick="deleteRule(\''+r.id+'\')">Delete</button></td></tr>').join('')+'</tbody></table>';
}
async function createRule(){
  const id=document.getElementById('rule-id').value; const name=document.getElementById('rule-name').value;
  const desc=document.getElementById('rule-desc').value; const condition=document.getElementById('rule-condition').value;
  const action=document.getElementById('rule-action').value; const severity=document.getElementById('rule-severity').value;
  let config={}; try{config=JSON.parse(document.getElementById('rule-config').value||'{}')}catch(e){toast('Invalid action config JSON',true);return}
  if(!id||!name){toast('Rule ID and Name required',true);return}
  const r=await api('POST','/api/panteon/rules/create',{id,name,description:desc,trigger_condition:condition,action_type:action,action_config:config,severity});
  if(r.status==='created'){toast('Rule created: '+id);loadBuilderRules()}else{toast(r.error||'Failed',true)}
}
async function toggleRule(id,enabled){const r=await api('POST','/api/panteon/rules/toggle',{rule_id:id,enabled});if(r.rule_id){toast((enabled?'Enabled':'Disabled')+': '+id);loadBuilderRules();loadDashboard()}else{toast('Failed',true)}}
async function deleteRule(id){if(!confirm('Delete rule '+id+'?'))return;const r=await api('POST','/api/panteon/rules/delete',{id});if(r.status==='deleted'){toast('Deleted: '+id);loadBuilderRules();loadDashboard()}else{toast(r.error||'Failed',true)}}

// ── Notification Channels ─────────────────────────────────
async function loadChannels(){
  const d=await api('GET','/api/panteon/channels');
  const div=document.getElementById('channels-list');
  div.innerHTML='<table><thead><tr><th>ID</th><th>Company</th><th>Type</th><th>URL</th><th>Enabled</th></tr></thead><tbody>'+
    (d.channels||[]).map(c=>'<tr><td style="font-family:monospace;font-size:.75rem">'+c.id+'</td><td>'+c.company_id+'</td><td>'+c.channel_type+'</td><td style="font-size:.75rem;max-width:200px;overflow:hidden;text-overflow:ellipsis">'+(c.webhook_url||'')+'</td><td><span class="badge badge-'+(c.enabled?'enabled':'disabled')+'">'+(c.enabled?'enabled':'disabled')+'</span></td></tr>').join('')+'</tbody></table>';
}
async function registerChannel(){
  const id=document.getElementById('chan-id').value; const company=document.getElementById('chan-company').value;
  const type=document.getElementById('chan-type').value; const url=document.getElementById('chan-url').value;
  if(!id){toast('Channel ID required',true);return}
  const r=await api('POST','/api/panteon/channels/register',{id,company_id:company,channel_type:type,webhook_url:url});
  if(r.status){toast('Channel registered: '+id);loadChannels()}else{toast(r.error||'Failed',true)}
}

// ── Ingestion ──────────────────────────────────────────────
async function registerSource(){const r=await api('POST','/api/panteon/ingest',{source_type:document.getElementById('reg-type').value,source_name:document.getElementById('reg-name').value,company_id:document.getElementById('reg-company').value});if(r.source_id){toast('Source registered: '+r.source_id);loadDashboard()}else{toast(r.error||'Failed',true)}}
async function ingestData(){let payload;try{payload=JSON.parse(document.getElementById('ingest-payload').value)}catch(e){toast('Invalid JSON',true);return}const r=await api('POST','/api/panteon/ingest',{source_id:document.getElementById('ingest-source').value,company_id:document.getElementById('reg-company').value,data_type:document.getElementById('ingest-type').value,payload:payload});if(r.status==='ingested'){toast('Data ingested: record #'+r.record_id);loadDashboard()}else{toast(r.error||'Failed',true)}}
async function processAll(){const r=await api('POST','/api/panteon/process',{limit:100});toast('Processed '+r.processed+' records');loadDashboard()}
async function runOntology(){const r=await api('POST','/api/panteon/enrich',{});toast('Enriched '+r.enriched.enriched+' entities, '+r.risk_patterns.patterns_detected+' patterns');loadDashboard();loadGraph()}
async function runEvaluate(){const r=await api('POST','/api/panteon/evaluate',{});toast(r.executions+' actions triggered');loadDashboard()}

// ── Init ───────────────────────────────────────────────────
loadDashboard();
loadPipelineStats();
loadGraph();
loadBuilderRules();
loadChannels();
setInterval(loadDashboard,30000);
setInterval(loadPipelineStats,30000);
setInterval(loadGraph,60000);
</script>
</body>
</html>'''


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
