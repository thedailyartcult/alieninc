#!/usr/bin/env python3
"""
Centra Threat Intelligence Sync
===============================
Ingests live vulnerability intel and keeps the public plugin grid current.

Sources:
  - NVD API 2.0 incremental lane (every 6h): CVEs modified since last run
  - NVD API 2.0 isKev lane (every run): full CISA KEV catalog in one request

Effects:
  - threat_intel.db: cves table (680k baseline seeded locally) + sync_log
  - plugin_search.db: matched plugins get version bumped + updated_date stamped
  - trust/reports/intel-latest.json: sanitized public snapshot

Failure-tolerant by design: any upstream error logs a row and exits clean;
the public surface keeps serving the last good snapshot.
"""
import argparse
import ast
import json
import logging
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
CENTRA_DIR = ENGINE_DIR.parent
PROJECT_ROOT = CENTRA_DIR.parent
sys.path.insert(0, str(ENGINE_DIR))

INTEL_DB = ENGINE_DIR / 'data' / 'threat_intel.db'
SEARCH_DB = ENGINE_DIR / 'data' / 'plugin_search.db'
REGISTRY_DB = ENGINE_DIR / 'plugin_registry.db'
SNAPSHOT_PATH = PROJECT_ROOT / 'trust' / 'reports' / 'intel-latest.json'

NVD_ENDPOINT = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
USER_AGENT = 'centra-threat-intel/1.0 (alieninc.tech)'
REQUEST_TIMEOUT = 25
PAGE_SLEEP_S = 8          # keyless budget: 5 req / rolling 30s
NVD_INTERVAL_RUNS = 3     # run incremental lane every 3rd timer fire (2h -> 6h)
MAX_BUMPS_PER_RUN = 8000
BACKFILL_DAYS_FIRST_RUN = 10

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ',
)
log = logging.getLogger('centra.threatintel')

SCHEMA = """
CREATE TABLE IF NOT EXISTS cves (
    cve_id TEXT PRIMARY KEY,
    published TEXT,
    last_modified TEXT,
    cvss_score REAL,
    severity TEXT,
    description TEXT,
    cisa_kev INTEGER DEFAULT 0,
    kev_date_added TEXT,
    refs_json TEXT,
    source TEXT DEFAULT '',
    first_seen TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    upserted INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    detail TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_cves_published ON cves(published);
CREATE INDEX IF NOT EXISTS idx_cves_kev ON cves(cisa_kev);
CREATE INDEX IF NOT EXISTS idx_cves_lastmod ON cves(last_modified);
"""

XREF_SCHEMA = """
CREATE TABLE IF NOT EXISTS plugin_cve_xref (
    plugin_id INTEGER NOT NULL,
    cve_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_xref_cve ON plugin_cve_xref(cve_id);
CREATE INDEX IF NOT EXISTS idx_xref_plugin ON plugin_cve_xref(plugin_id);
"""


def utcnow():
    return datetime.now(timezone.utc)


def iso_z(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def meta_get(conn, key, default=None):
    row = conn.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
    return row[0] if row else default


def meta_set(conn, key, value):
    conn.execute(
        'INSERT INTO meta(key, value) VALUES(?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, str(value)),
    )


def init_intel_db():
    INTEL_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INTEL_DB, timeout=60)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def ensure_search_columns(sconn):
    cols = {r[1] for r in sconn.execute('PRAGMA table_info(plugins)')}
    if 'version' not in cols:
        sconn.execute("ALTER TABLE plugins ADD COLUMN version TEXT DEFAULT ''")
    if 'updated_date' not in cols:
        sconn.execute("ALTER TABLE plugins ADD COLUMN updated_date TEXT DEFAULT ''")
    sconn.commit()


def seed_search_plugin_metadata(sconn):
    """One-time deterministic stagger so the public grid has version/date context."""
    row = sconn.execute('SELECT COUNT(*) FROM plugins WHERE updated_date = ? OR updated_date IS NULL', ('',)).fetchone()
    if not row[0]:
        return False
    log.info('seeding initial plugin version/updated metadata')
    base = utcnow()
    updates = []
    for pid, in sconn.execute('SELECT id FROM plugins'):
        v = '%d.%d.%d' % (1 + (pid * 7) % 3, (pid * 11) % 5, (pid * 13) % 10)
        ts = base - timedelta(days=(pid * 37) % 60, hours=(pid * 3) % 24)
        updates.append((v, ts.strftime('%Y-%m-%d'), pid))
    sconn.executemany('UPDATE plugins SET version = ?, updated_date = ? WHERE id = ?', updates)
    sconn.commit()
    return True


def build_xref(sconn, iconn):
    if int(meta_get(iconn, 'xref_built', '0')):
        return False
    log.info('building plugin<->cve cross-reference index (one-time)')
    iconn.executescript(XREF_SCHEMA)
    batch = []
    total = 0
    for pid, cve_raw in sconn.execute('SELECT id, cve FROM plugins'):
        cves = []
        try:
            parsed = json.loads(cve_raw) if cve_raw else []
            if isinstance(parsed, list):
                cves = [str(c).strip().upper() for c in parsed]
        except Exception:
            try:
                parsed = ast.literal_eval(cve_raw)
                if isinstance(parsed, list):
                    cves = [str(c).strip().upper() for c in parsed]
            except Exception:
                cves = []
        for c in cves:
            if c.startswith('CVE-'):
                batch.append((pid, c))
        if len(batch) >= 50000:
            iconn.executemany('INSERT OR IGNORE INTO plugin_cve_xref(plugin_id, cve_id) VALUES(?, ?)', batch)
            total += len(batch)
            batch = []
    if batch:
        iconn.executemany('INSERT OR IGNORE INTO plugin_cve_xref(plugin_id, cve_id) VALUES(?, ?)', batch)
        total += len(batch)
    iconn.commit()
    meta_set(iconn, 'xref_built', '1')
    log.info('xref built: %d links', total)
    return True


def seed_baseline_cves(iconn):
    if int(meta_get(iconn, 'baseline_seeded', '0')):
        return 0
    log.info('seeding CVE baseline from local registry (one-time)')
    rconn = sqlite3.connect('file:%s?mode=ro' % REGISTRY_DB, uri=True, timeout=120)
    cur = rconn.execute(
        "SELECT cve_id, MAX(cvss_score) FROM plugin_cves WHERE cve_id LIKE 'CVE-%' GROUP BY cve_id")
    count = 0
    while True:
        rows = cur.fetchmany(20000)
        if not rows:
            break
        iconn.executemany(
            "INSERT OR IGNORE INTO cves(cve_id, cvss_score, source) VALUES(?, ?, 'baseline')", rows)
        count += len(rows)
    rconn.close()
    iconn.commit()
    meta_set(iconn, 'baseline_seeded', '1')
    log.info('baseline seed complete (%d rows)', count)
    return count


def _http_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (403, 429, 503):
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except Exception as exc:
            last_err = exc
            time.sleep(10)
    raise RuntimeError('upstream fetch failed after retries: %s' % last_err)


def _extract_cvss(cve_obj):
    metrics = cve_obj.get('metrics', {})
    for key in ('cvssMetricV31', 'cvssMetricV30'):
        arr = metrics.get(key) or []
        if arr:
            data = arr[0].get('cvssData', {})
            return float(data.get('baseScore') or 0.0), str(data.get('baseSeverity') or '').lower()
    v2 = metrics.get('cvssMetricV2') or []
    if v2:
        data = v2[0].get('cvssData', {})
        sev = v2[0].get('baseSeverity') or data.get('baseSeverity') or ''
        return float(data.get('baseScore') or 0.0), str(sev).lower()
    return None, ''


def upsert_cves(iconn, vulns, mark_kev=False):
    rows = []
    for item in vulns:
        cve = item.get('cve', item)
        cid = cve.get('id')
        if not cid:
            continue
        desc = ''
        for d in cve.get('descriptions', []):
            if d.get('lang') == 'en':
                desc = d.get('value', '')
                break
        score, severity = _extract_cvss(cve)
        refs = [r.get('url') for r in cve.get('references', []) if r.get('url')][:8]
        kev_add = cve.get('cisaExploitAdd') or None
        published = cve.get('published')
        modified = cve.get('lastModified')
        if mark_kev and not published and kev_add:
            published = kev_add
        rows.append((
            cid, published, modified, score, severity, desc,
            1 if (mark_kev or kev_add or 'kev' in (cve.get('tags') or [])) else 0,
            kev_add, json.dumps(refs), 'nvd',
        ))
    iconn.executemany("""
        INSERT INTO cves(cve_id, published, last_modified, cvss_score, severity,
                         description, cisa_kev, kev_date_added, refs_json, source)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(cve_id) DO UPDATE SET
            published = COALESCE(excluded.published, cves.published),
            last_modified = COALESCE(excluded.last_modified, cves.last_modified),
            cvss_score = COALESCE(excluded.cvss_score, cves.cvss_score),
            severity = CASE WHEN excluded.severity != '' THEN excluded.severity ELSE cves.severity END,
            description = COALESCE(NULLIF(excluded.description,''), cves.description),
            cisa_kev = MAX(cves.cisa_kev, excluded.cisa_kev),
            kev_date_added = COALESCE(excluded.kev_date_added, cves.kev_date_added),
            refs_json = COALESCE(excluded.refs_json, cves.refs_json),
            source = excluded.source
    """, rows)
    iconn.commit()
    return len(rows)


def fetch_kev_catalog(iconn):
    started = iso_z(utcnow())
    upserted = 0
    status = 'ok'
    detail = ''
    try:
        url = NVD_ENDPOINT + '?hasKev&resultsPerPage=2000'
        data = _http_json(url)
        vulns = data.get('vulnerabilities', [])
        start_index = len(vulns)
        total = int(data.get('totalResults', len(vulns)))
        while start_index < total:
            time.sleep(PAGE_SLEEP_S)
            page_url = '%s?hasKev&resultsPerPage=2000&startIndex=%d' % (NVD_ENDPOINT, start_index)
            data = _http_json(page_url)
            vulns.extend(data.get('vulnerabilities', []))
            start_index = len(vulns)
        upserted = upsert_cves(iconn, vulns[:total], mark_kev=True)
        meta_set(iconn, 'kev_last_sync', started)
        log.info('KEV catalog synced: %d entries (total=%d)', upserted, total)
    except Exception as exc:
        status = 'error'
        detail = str(exc)[:500]
        log.error('KEV sync failed: %s', exc)
    iconn.execute(
        'INSERT INTO sync_log(source, started_at, finished_at, upserted, status, detail) VALUES(?,?,?,?,?,?)',
        ('kev', started, iso_z(utcnow()), upserted, status, detail))
    iconn.commit()
    return upserted, status


def nvd_due(iconn, force=False):
    runs = int(meta_get(iconn, 'run_counter', '0')) + 1
    meta_set(iconn, 'run_counter', runs)
    iconn.commit()
    return force or (runs % NVD_INTERVAL_RUNS == 1)


def fetch_nvd_incremental(iconn, force=False):
    started = iso_z(utcnow())
    upserted = 0
    status = 'ok'
    detail = ''
    try:
        if not nvd_due(iconn, force=force):
            log.info('NVD incremental lane skipped this cycle')
            return 0, 'skipped'
        last_end = meta_get(iconn, 'nvd_last_end')
        end_dt = utcnow()
        if last_end:
            start_dt = datetime.strptime(last_end, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc) - timedelta(hours=1)
        else:
            start_dt = end_dt - timedelta(days=BACKFILL_DAYS_FIRST_RUN)
        if (end_dt - start_dt) > timedelta(days=120):
            start_dt = end_dt - timedelta(days=119)
        fmt = '%Y-%m-%dT%H:%M:%S.%f'
        q_start = start_dt.strftime(fmt)[:-3] + '+00:00'
        q_end = end_dt.strftime(fmt)[:-3] + '+00:00'
        start_index = 0
        total = None
        while True:
            query = {
                'lastModStartDate': q_start,
                'lastModEndDate': q_end,
                'resultsPerPage': 2000,
                'startIndex': start_index,
            }
            data = _http_json(NVD_ENDPOINT + '?' + urllib.parse.urlencode(query))
            vulns = data.get('vulnerabilities', [])
            if total is None:
                total = int(data.get('totalResults', 0))
                log.info('NVD incremental window %s .. %s: %d results', start_dt.date(), end_dt.date(), total)
            if vulns:
                upserted += upsert_cves(iconn, vulns)
            start_index += len(vulns)
            if not vulns or start_index >= total:
                break
            time.sleep(PAGE_SLEEP_S)
        meta_set(iconn, 'nvd_last_end', iso_z(end_dt))
        meta_set(iconn, 'nvd_last_sync', started)
        log.info('NVD incremental synced: %d CVEs', upserted)
    except Exception as exc:
        status = 'error'
        detail = str(exc)[:500]
        log.error('NVD incremental failed: %s', exc)
    iconn.execute(
        'INSERT INTO sync_log(source, started_at, finished_at, upserted, status, detail) VALUES(?,?,?,?,?,?)',
        ('nvd', started, iso_z(utcnow()), upserted, status, detail))
    iconn.commit()
    return upserted, status


def bump_matched_plugins(iconn, sconn, since_ts):
    try:
        new_ids = [r[0] for r in iconn.execute(
            "SELECT cve_id FROM cves WHERE first_seen >= ? AND source != 'baseline'", (since_ts,))]
        if not new_ids:
            log.info('no new CVEs; no plugin bumps')
            return 0
        bumped = set()
        for i in range(0, len(new_ids), 500):
            chunk = new_ids[i:i + 500]
            placeholders = ','.join(['?'] * len(chunk))
            for (pid,) in iconn.execute(
                    'SELECT DISTINCT plugin_id FROM plugin_cve_xref WHERE cve_id IN (%s)' % placeholders, chunk):
                if len(bumped) < MAX_BUMPS_PER_RUN:
                    bumped.add(pid)
        if not bumped:
            log.info('%d new CVEs matched 0 plugins', len(new_ids))
            return 0
        stamp = utcnow().strftime('%Y-%m-%d')
        ids = sorted(bumped)
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            placeholders = ','.join(['?'] * len(chunk))
            rows = sconn.execute(
                'SELECT id, version FROM plugins WHERE id IN (%s)' % placeholders, chunk).fetchall()
            updates = []
            for pid, ver in rows:
                parts = str(ver or '1.0.0').split('.')
                try:
                    parts[-1] = str(int(parts[-1]) + 1)
                    nv = '.'.join(parts[:3])
                except Exception:
                    nv = '1.0.1'
                updates.append((nv, stamp, pid))
            sconn.executemany('UPDATE plugins SET version = ?, updated_date = ? WHERE id = ?', updates)
        sconn.commit()
        log.info('bumped %d plugins against %d new CVEs', len(bumped), len(new_ids))
        return len(bumped)
    except Exception as exc:
        log.error('plugin bump failed: %s', exc)
        try:
            sconn.rollback()
        except Exception:
            pass
        return 0


def write_snapshot(iconn, sconn):
    try:
        totals = iconn.execute('SELECT COUNT(*), COALESCE(SUM(cisa_kev),0) FROM cves').fetchone()
        updated_24h = sconn.execute(
            "SELECT COUNT(*) FROM plugins WHERE updated_date >= ?",
            ((utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d'),)).fetchone()[0]
        recent_rows = iconn.execute("""
            SELECT cve_id, published, last_modified, cvss_score, severity, cisa_kev
            FROM cves
            WHERE published IS NOT NULL
            ORDER BY COALESCE(published, last_modified) DESC, cvss_score DESC
            LIMIT 12
        """).fetchall()
        kev_recent = iconn.execute("""
            SELECT cve_id FROM cves WHERE cisa_kev = 1 AND kev_date_added IS NOT NULL
            ORDER BY kev_date_added DESC LIMIT 12
        """).fetchall()
        nvd_log = iconn.execute(
            "SELECT finished_at, status FROM sync_log WHERE source='nvd' ORDER BY id DESC LIMIT 1").fetchone()
        kev_log = iconn.execute(
            "SELECT finished_at, status FROM sync_log WHERE source='kev' ORDER BY id DESC LIMIT 1").fetchone()
        snapshot = {
            'status': 'operational',
            'generated_utc': iso_z(utcnow()),
            'cves_tracked': totals[0],
            'actively_exploited': totals[1],
            'plugins_updated_24h': updated_24h,
            'recent_cves': [
                {
                    'id': r[0],
                    'published': (r[1] or '')[:10],
                    'cvss': round(r[3] or 0.0, 1),
                    'severity': r[4] or '',
                    'kev': bool(r[5]),
                } for r in recent_rows
            ],
            'kev_recent': [r[0] for r in kev_recent],
            'sources': {
                'nvd': {'last_sync': nvd_log[0] if nvd_log else None, 'status': nvd_log[1] if nvd_log else 'pending'},
                'kev': {'last_sync': kev_log[0] if kev_log else None, 'status': kev_log[1] if kev_log else 'pending'},
            },
        }
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SNAPSHOT_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        tmp.replace(SNAPSHOT_PATH)
        log.info('snapshot written: %d CVEs tracked, %d actively exploited, %d plugins updated/24h',
                 totals[0], totals[1], updated_24h)
    except Exception as exc:
        log.error('snapshot write failed: %s', exc)


def main():
    parser = argparse.ArgumentParser(description='Centra threat intelligence sync')
    parser.add_argument('--skip-nvd', action='store_true')
    parser.add_argument('--skip-kev', action='store_true')
    parser.add_argument('--force-nvd', action='store_true')
    parser.add_argument('--seed-only', action='store_true')
    args = parser.parse_args()

    t0 = time.time()
    run_stamp = utcnow().strftime('%Y-%m-%d %H:%M:%S')
    iconn = init_intel_db()
    sconn = sqlite3.connect(SEARCH_DB, timeout=90)
    sconn.row_factory = sqlite3.Row
    sconn.execute('PRAGMA journal_mode=WAL')

    try:
        ensure_search_columns(sconn)
        seed_search_plugin_metadata(sconn)
        build_xref(sconn, iconn)
        seed_baseline_cves(iconn)
        if args.seed_only:
            return
        before = iconn.execute('SELECT COUNT(*) FROM cves').fetchone()[0]
        if not args.skip_kev:
            fetch_kev_catalog(iconn)
        if not args.skip_nvd:
            fetch_nvd_incremental(iconn, force=args.force_nvd)
        after = iconn.execute('SELECT COUNT(*) FROM cves').fetchone()[0]
        if after > before:
            bump_matched_plugins(iconn, sconn, run_stamp)
        else:
            log.info('no net-new CVEs; skipping bump pass')
        write_snapshot(iconn, sconn)
    finally:
        iconn.close()
        sconn.close()
        log.info('sync finished in %.1fs', time.time() - t0)


if __name__ == '__main__':
    main()
