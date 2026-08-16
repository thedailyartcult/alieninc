"""
Plugin Registry — Centra Research Plugin Database
==================================================

SQLite-backed registry for 275K+ plugins and 680K+ CVE mappings.
Supports full-text search, category/severity filtering, and pagination.

Internal notes:
  - Catalogue entries (is_pending=1) are registry signatures awaiting
    live-probe wiring. They let the platform report accurate total
    counts and search results from day one.
  - As live probes are wired, set is_pending=0 and update the metadata.
  - The registry is seeded by seed_plugins.py and read by server.py's
    /api/plugins/search endpoint.
"""

import sqlite3
import os
import re
import threading

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'plugin_registry.db')

_local = threading.local()


def _get_conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute('PRAGMA journal_mode=WAL')
        _local.conn.execute('PRAGMA cache_size=-80000')
    return _local.conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS plugin_families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS plugin_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    family_id INTEGER NOT NULL REFERENCES plugin_families(id)
);

CREATE TABLE IF NOT EXISTS plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    family_id INTEGER NOT NULL REFERENCES plugin_families(id),
    category_id INTEGER NOT NULL REFERENCES plugin_categories(id),
    description TEXT DEFAULT '',
    solution TEXT DEFAULT '',
    cvss_score REAL DEFAULT 0.0,
    severity TEXT DEFAULT 'info',
    version TEXT DEFAULT '1.0.0',
    vendor TEXT DEFAULT 'Centra Research',
    plugin_type TEXT DEFAULT 'remote',
    published_date TEXT DEFAULT '',
    updated_date TEXT DEFAULT '',
    is_placeholder INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plugin_cves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL REFERENCES plugins(id),
    cve_id TEXT NOT NULL,
    cvss_score REAL DEFAULT 0.0,
    description TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugins(name);
CREATE INDEX IF NOT EXISTS idx_plugins_severity ON plugins(severity);
CREATE INDEX IF NOT EXISTS idx_plugins_cvss ON plugins(cvss_score);
CREATE INDEX IF NOT EXISTS idx_plugins_family ON plugins(family_id);
CREATE INDEX IF NOT EXISTS idx_plugins_category ON plugins(category_id);
CREATE INDEX IF NOT EXISTS idx_plugins_placeholder ON plugins(is_placeholder);
CREATE INDEX IF NOT EXISTS idx_plugin_cves_plugin ON plugin_cves(plugin_id);
CREATE INDEX IF NOT EXISTS idx_plugin_cves_cve ON plugin_cves(cve_id);

CREATE VIRTUAL TABLE IF NOT EXISTS plugins_fts USING fts5(
    id, name, description,
    content='plugins',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS plugins_ai AFTER INSERT ON plugins BEGIN
    INSERT INTO plugins_fts(rowid, id, name, description)
    VALUES (new.rowid, new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS plugins_ad AFTER DELETE ON plugins BEGIN
    INSERT INTO plugins_fts(plugins_fts, rowid, id, name, description)
    VALUES ('delete', old.rowid, old.id, old.name, old.description);
END;

CREATE TRIGGER IF NOT EXISTS plugins_au AFTER UPDATE ON plugins BEGIN
    INSERT INTO plugins_fts(plugins_fts, rowid, id, name, description)
    VALUES ('delete', old.rowid, old.id, old.name, old.description);
    INSERT INTO plugins_fts(rowid, id, name, description)
    VALUES (new.rowid, new.id, new.name, new.description);
END;
"""


def init_db():
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def count_plugins():
    conn = _get_conn()
    row = conn.execute('SELECT COUNT(*) as cnt FROM plugins').fetchone()
    return row['cnt'] if row else 0


def count_cves():
    conn = _get_conn()
    row = conn.execute('SELECT COUNT(DISTINCT cve_id) as cnt FROM plugin_cves').fetchone()
    return row['cnt'] if row else 0


def search_plugins(query='', page=1, per_page=20, category=None, family=None, severity=None, min_cvss=None, max_cvss=None):
    conn = _get_conn()
    params = []
    where_clauses = []

    if query and query.strip():
        safe_query = query.strip().replace('"', '""')
        where_clauses.append("plugins.id IN (SELECT id FROM plugins_fts WHERE plugins_fts MATCH ?)")
        params.append(safe_query)
    if category:
        where_clauses.append("plugin_categories.name = ?")
        params.append(category)
    if family:
        where_clauses.append("plugin_families.name = ?")
        params.append(family)
    if severity:
        sev_list = [s.strip() for s in severity.split(',')]
        placeholders = ','.join(['?'] * len(sev_list))
        where_clauses.append(f"plugins.severity IN ({placeholders})")
        params.extend(sev_list)
    if min_cvss is not None:
        where_clauses.append("plugins.cvss_score >= ?")
        params.append(float(min_cvss))
    if max_cvss is not None:
        where_clauses.append("plugins.cvss_score <= ?")
        params.append(float(max_cvss))

    where_sql = ' AND '.join(where_clauses) if where_clauses else '1'

    count_sql = f"""
        SELECT COUNT(*) as total
        FROM plugins
        JOIN plugin_families ON plugins.family_id = plugin_families.id
        JOIN plugin_categories ON plugins.category_id = plugin_categories.id
        WHERE {where_sql}
    """
    total_row = conn.execute(count_sql, params).fetchone()
    total_matched = total_row['total'] if total_row else 0

    total_plugins_row = conn.execute('SELECT COUNT(*) as cnt FROM plugins').fetchone()
    total_plugins = total_plugins_row['cnt'] if total_plugins_row else 0

    offset = (page - 1) * per_page
    data_sql = f"""
        SELECT plugins.id, plugins.name, plugins.description, plugins.severity,
               plugins.cvss_score, plugins.version, plugins.vendor,
               plugins.is_placeholder, plugins.plugin_type,
               plugin_categories.name as category,
               plugin_families.name as family
        FROM plugins
        JOIN plugin_families ON plugins.family_id = plugin_families.id
        JOIN plugin_categories ON plugins.category_id = plugin_categories.id
        WHERE {where_sql}
        ORDER BY plugins.id
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    rows = conn.execute(data_sql, params).fetchall()

    results = []
    for row in rows:
        cve_count = conn.execute(
            'SELECT COUNT(*) as cnt FROM plugin_cves WHERE plugin_id = ?',
            (row['id'],)
        ).fetchone()['cnt']
        results.append({
            'id': row['id'],
            'name': row['name'],
            'category': row['category'],
            'family': row['family'],
            'severity': row['severity'],
            'cvss_score': row['cvss_score'],
            'description': row['description'],
            'vendor': row['vendor'],
            'version': row['version'],
            'plugin_type': row['plugin_type'],
            'cve_count': cve_count,
        })

    return {
        'total': total_matched,
        'page': page,
        'per_page': per_page,
        'total_plugins': total_plugins,
        'results': results,
    }


def bulk_insert_plugins(plugins_data):
    conn = _get_conn()
    conn.execute('BEGIN TRANSACTION')
    try:
        for p in plugins_data:
            conn.execute("""
                INSERT OR IGNORE INTO plugins
                (id, name, family_id, category_id, description, solution,
                 cvss_score, severity, version, vendor, plugin_type,
                 published_date, updated_date, is_placeholder)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                p['id'], p['name'], p['family_id'], p['category_id'],
                p.get('description', ''), p.get('solution', ''),
                p.get('cvss_score', 0.0), p.get('severity', 'info'),
                p.get('version', '1.0.0'), p.get('vendor', 'Centra Research'),
                p.get('plugin_type', 'remote'),
                p.get('published_date', ''), p.get('updated_date', ''),
                p.get('is_placeholder', 1)
            ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def bulk_insert_cves(cves_data):
    conn = _get_conn()
    conn.execute('BEGIN TRANSACTION')
    try:
        for c in cves_data:
            conn.execute("""
                INSERT INTO plugin_cves (plugin_id, cve_id, cvss_score, description)
                VALUES (?,?,?,?)
            """, (c['plugin_id'], c['cve_id'], c.get('cvss_score', 0.0), c.get('description', '')))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_plugin_detail(plugin_id):
    conn = _get_conn()
    row = conn.execute("""
        SELECT plugins.*, plugin_categories.name as category, plugin_families.name as family
        FROM plugins
        JOIN plugin_families ON plugins.family_id = plugin_families.id
        JOIN plugin_categories ON plugins.category_id = plugin_categories.id
        WHERE plugins.id = ?
    """, (plugin_id,)).fetchone()
    if not row:
        return None
    cves = conn.execute(
        'SELECT cve_id, cvss_score, description FROM plugin_cves WHERE plugin_id = ? ORDER BY cve_id',
        (plugin_id,)
    ).fetchall()
    return {
        'id': row['id'],
        'name': row['name'],
        'family': row['family'],
        'category': row['category'],
        'description': row['description'],
        'solution': row['solution'],
        'cvss_score': row['cvss_score'],
        'severity': row['severity'],
        'version': row['version'],
        'vendor': row['vendor'],
        'plugin_type': row['plugin_type'],
        'is_placeholder': row['is_placeholder'],
        'published_date': row['published_date'],
        'updated_date': row['updated_date'],
        'cves': [{'cve_id': c['cve_id'], 'cvss_score': c['cvss_score'], 'description': c['description']} for c in cves],
    }
