#!/usr/bin/env python3
"""
Statute & Precedent — WAT Runner (Python wrapper)
==================================================
Calls the Node.js WAT runner, parses results, and stores
web audit findings in the compliance SQLite database.

Usage:
    python3 wat_runner.py                  # Audit all companies
    python3 wat_runner.py --company alieninc  # Audit one company
    python3 wat_runner.py --report         # Just show latest report
"""

import json
import subprocess
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "compliance.db"
REPORTS_DIR = ENGINE_DIR / "wat_reports"
COMBINED_REPORT = REPORTS_DIR / "combined_report.json"

# Company ID to name mapping — must match wat_runner.js COMPANIES keys
COMPANY_NAMES = {
    "alieninc":         {"name": "Alien.Inc",                "url": "https://alieninc.tech/"},
    "1609holdings":     {"name": "1609 Holdings",           "url": "https://1609.alieninc.tech"},
    "exosphere":        {"name": "Exosphere",               "url": "https://exosphere.alieninc.tech"},
    "panteon":        {"name": "Panteon",               "url": "https://panteon.alieninc.tech"},
    "kmt":              {"name": "KMT Consulting Group",    "url": "https://kmt.alieninc.tech"},
    "thedailyartcult":  {"name": "The Daily Art Cult",      "url": "https://thedailyartcult.lol"},
    "alcantara":        {"name": "St. Alcantara Foundation","url": "https://stalcantara.alieninc.tech"},
}


def init_web_audits_table(conn):
    """Create the web_audits table if it doesn't exist."""
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS web_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            company_id TEXT NOT NULL,
            cookies_total INTEGER DEFAULT 0,
            cookies_first_party INTEGER DEFAULT 0,
            cookies_third_party INTEGER DEFAULT 0,
            cookies_session INTEGER DEFAULT 0,
            cookies_persistent INTEGER DEFAULT 0,
            trackers_total INTEGER DEFAULT 0,
            tracker_lists TEXT DEFAULT '[]',
            hosts_total INTEGER DEFAULT 0,
            hosts_first_party INTEGER DEFAULT 0,
            hosts_third_party INTEGER DEFAULT 0,
            https_enabled INTEGER DEFAULT 0,
            https_redirect INTEGER DEFAULT 0,
            security_headers_score INTEGER DEFAULT 0,
            security_headers_missing TEXT DEFAULT '[]',
            localstorage_items INTEGER DEFAULT 0,
            web_compliance_score INTEGER DEFAULT 0,
            raw_report TEXT DEFAULT '{}'
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_audits_company
        ON web_audits (company_id, scan_date)
    """)
    conn.commit()


def compute_web_compliance_score(audit):
    """Compute a 0-100 web compliance score from audit data.
    
    NOTE: Point deductions are based on regulatory requirements where applicable.
    Where no specific regulation mandates a technical measure, it is labeled as
    "best practice" rather than a compliance requirement.
    """
    score = 100

    # HTTPS check — Art. 32 recommends encryption as appropriate technical measure
    if not audit.get('https', {}).get('https_support', False):
        score -= 10

    # Third-party cookies — ePrivacy Directive Art. 5(3) requires consent
    cookies = audit.get('cookies', [])
    third_party = [c for c in cookies if not c.get('firstPartyStorage', True)]
    if len(third_party) > 0:
        score -= min(15, len(third_party) * 5)

    # Trackers — GDPR Art. 6 requires lawful basis for tracking
    beacons = audit.get('beacons', [])
    if len(beacons) > 0:
        score -= min(20, len(beacons) * 5)

    # Security headers — Art. 32 / Art. 5(1)(f) integrity and confidentiality
    headers = audit.get('security_headers', {})
    critical_headers = ['content-security-policy', 'strict-transport-security',
                        'x-frame-options', 'x-content-type-options']
    missing = [h for h in critical_headers if not headers.get(h)]
    if missing:
        score -= min(15, len(missing) * 5)

    # localStorage — Art. 5(1)(c) data minimisation principle
    ls = audit.get('localstorage', [])
    if len(ls) > 10:
        score -= min(5, (len(ls) - 10))

    # Third-party hosts — Art. 13(1)(e) requires recipient disclosure
    hosts = audit.get('hosts', [])
    third_party_hosts = [h for h in hosts if not h.get('firstParty', True)]
    if len(third_party_hosts) > 5:
        score -= min(5, (len(third_party_hosts) - 5))

    return max(0, score)


def run_wat_scan(company_id=None):
    """Run the Node.js WAT runner and store results."""
    cmd = ['node', str(ENGINE_DIR / 'wat_runner.js')]
    if company_id:
        info = COMPANY_NAMES.get(company_id)
        if not info:
            print(f"Unknown company: {company_id}")
            return None
        cmd.extend(['--url', info['url']])

    print("Running EDPB WAT web audit...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"WAT runner error: {result.stderr}")
        return None

    print(result.stdout)
    return load_and_store_results()


def load_and_store_results():
    """Load the combined report and store in the database."""
    if not COMBINED_REPORT.exists():
        print("No WAT report found. Run the scanner first.")
        return None

    with open(COMBINED_REPORT) as f:
        report = json.load(f)

    conn = sqlite3.connect(str(DB_PATH))
    init_web_audits_table(conn)
    c = conn.cursor()
    scan_date = report.get('report_date', datetime.now().isoformat())
    scores = {}

    for company_id, audit in report.get('companies', {}).items():
        if 'error' in audit:
            print(f"  {company_id}: Error — {audit['error']}")
            continue

        score = compute_web_compliance_score(audit)
        scores[company_id] = score

        cookies = audit.get('cookies', [])
        hosts = audit.get('hosts', [])
        beacons = audit.get('beacons', [])

        first_party_cookies = [c for c in cookies if c.get('firstPartyStorage', True)]
        third_party_cookies = [c for c in cookies if not c.get('firstPartyStorage', True)]
        session_cookies = [c for c in cookies if c.get('session', False)]
        persistent_cookies = [c for c in cookies if not c.get('session', False)]

        first_party_hosts = [h for h in hosts if h.get('firstParty', True)]
        third_party_hosts = [h for h in hosts if not h.get('firstParty', True)]

        tracker_lists = list(set(b.get('listName', '') for b in beacons))

        headers = audit.get('security_headers', {})
        critical_headers = ['content-security-policy', 'strict-transport-security',
                            'x-frame-options', 'x-content-type-options',
                            'referrer-policy', 'permissions-policy']
        headers_score = sum(1 for h in critical_headers if headers.get(h))
        headers_missing = [h for h in critical_headers if not headers.get(h)]

        c.execute("""
            INSERT INTO web_audits
            (scan_date, company_id, cookies_total, cookies_first_party,
             cookies_third_party, cookies_session, cookies_persistent,
             trackers_total, tracker_lists,
             hosts_total, hosts_first_party, hosts_third_party,
             https_enabled, https_redirect,
             security_headers_score, security_headers_missing,
             localstorage_items, web_compliance_score, raw_report)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_date, company_id,
            len(cookies), len(first_party_cookies), len(third_party_cookies),
            len(session_cookies), len(persistent_cookies),
            len(beacons), json.dumps(tracker_lists),
            len(hosts), len(first_party_hosts), len(third_party_hosts),
            1 if audit.get('https', {}).get('https_support') else 0,
            1 if audit.get('https', {}).get('https_redirect') else 0,
            headers_score, json.dumps(headers_missing),
            len(audit.get('localstorage', [])),
            score, json.dumps(audit),
        ))

        cinfo = COMPANY_NAMES.get(company_id, {"name": company_id})
        if isinstance(cinfo, dict):
            display_name = cinfo.get('name', company_id)
        else:
            display_name = str(cinfo)
        print(f"  {display_name}: {score}% web compliance")

    conn.commit()
    conn.close()
    return scores


def get_latest_web_report():
    """Get the latest web audit report from the database."""
    if not DB_PATH.exists():
        return None

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Check if table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='web_audits'")
    if not c.fetchone():
        conn.close()
        return None

    c.execute("""
        SELECT company_id, cookies_total, cookies_third_party,
               trackers_total, hosts_total, hosts_third_party,
               https_enabled, security_headers_score, security_headers_missing,
               localstorage_items, web_compliance_score, scan_date
        FROM web_audits
        WHERE id IN (SELECT MAX(id) FROM web_audits GROUP BY company_id)
        ORDER BY company_id
    """)

    results = []
    for row in c.fetchall():
        results.append({
            'company_id': row[0],
            'company_name': COMPANY_NAMES.get(row[0], row[0]),
            'cookies_total': row[1],
            'cookies_third_party': row[2],
            'trackers_total': row[3],
            'hosts_total': row[4],
            'hosts_third_party': row[5],
            'https_enabled': bool(row[6]),
            'security_headers_score': row[7],
            'security_headers_missing': json.loads(row[8]) if row[8] else [],
            'localstorage_items': row[9],
            'web_compliance_score': row[10],
            'scan_date': row[11],
        })

    conn.close()
    return results


if __name__ == "__main__":
    if '--report' in sys.argv:
        results = get_latest_web_report()
        if results:
            print(f"\n{'Company':30s} {'Score':>6s} {'Cookies':>8s} {'3P':>4s} {'Track':>6s} {'HTTPS':>6s} {'Headers':>8s}")
            print('─' * 80)
            for r in results:
                print(f"{r['company_name']:30s} {r['web_compliance_score']:>5}% {r['cookies_total']:>7d} {r['cookies_third_party']:>4d} {r['trackers_total']:>5d} {'yes' if r['https_enabled'] else 'NO':>6s} {r['security_headers_score']:>7d}/6")
        else:
            print("No web audit data available. Run a scan first.")
    else:
        company = None
        if '--company' in sys.argv:
            company = sys.argv[sys.argv.index('--company') + 1]
        run_wat_scan(company)
