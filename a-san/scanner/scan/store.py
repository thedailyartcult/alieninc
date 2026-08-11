"""SQLite-backed scan store: resumable queue, HTTP cache, parsed entries, catalog merge.

Thread-safety: one writer connection guarded by a lock; readers use a separate
read-only connection when needed. All writes are small and serialised.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import CatalogEntry, entry_to_json, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS urls (
    url          TEXT PRIMARY KEY,
    domain       TEXT NOT NULL,
    category     TEXT,               -- canonical category key or display name
    kind         TEXT DEFAULT 'product',   -- category | product | patent | sitemap
    state        TEXT DEFAULT 'queued',    -- queued | done | failed | skipped | disallowed
    robots       TEXT DEFAULT 'allow',      -- allow | disallow (robots.txt verdict)
    http_status  INTEGER,
    fetched_at   TEXT,
    html_hash    TEXT,
    attempts     INTEGER DEFAULT 0,
    error        TEXT,
    parsed       TEXT
);
CREATE TABLE IF NOT EXISTS raw_html (
    url        TEXT PRIMARY KEY REFERENCES urls(url) ON DELETE CASCADE,
    html       TEXT
);
CREATE TABLE IF NOT EXISTS entries (
    fingerprint  TEXT PRIMARY KEY,
    designation  TEXT,
    designation_key TEXT,
    category     TEXT,
    data         TEXT NOT NULL,
    source_url   TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_urls_state ON urls(state);
CREATE INDEX IF NOT EXISTS idx_urls_cat ON urls(category);
CREATE INDEX IF NOT EXISTS idx_entries_cat ON entries(category);
"""


class ScanStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self):
        """In-place upgrades for stores created by older schemas."""
        cols = [r["name"] for r in self._conn.execute("PRAGMA table_info(entries)")]
        if "designation_key" not in cols:
            self._conn.execute("ALTER TABLE entries ADD COLUMN designation_key TEXT")
            self._conn.execute(
                "UPDATE entries SET designation_key = LOWER(TRIM(designation)) "
                "WHERE designation_key IS NULL OR designation_key=''")
        self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_dk "
                           "ON entries(designation_key)")

    # ---------- urls queue ----------
    def enqueue(self, url: str, domain: str, category: str | None = None,
                kind: str = "product", robots: str = "allow"):
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO urls (url, domain, category, kind, robots) "
                "VALUES (?,?,?,?,?) ON CONFLICT(url) DO NOTHING",
                (url, domain, category, kind, robots))
            self._conn.commit()
            return cur.rowcount

    def next_batch(self, limit: int, categories: list[str] | None = None) -> list[dict]:
        with self._lock:
            if categories:
                ph = ",".join("?" * len(categories))
                rows = self._conn.execute(
                    f"SELECT * FROM urls WHERE state='queued' AND (category IN ({ph}) OR category IS NULL) "
                    "ORDER BY rowid LIMIT ?", (*categories, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM urls WHERE state='queued' ORDER BY rowid LIMIT ?",
                    (limit,)).fetchall()
            return [dict(r) for r in rows]

    def mark(self, url: str, state: str, error: str | None = None,
             status: int | None = None, html_hash: str | None = None):
        with self._lock:
            self._conn.execute(
                "UPDATE urls SET state=?, error=?, http_status=?, html_hash=?, "
                "attempts=attempts+1, fetched_at=? WHERE url=?",
                (state, error, status, html_hash, now_iso(), url))
            self._conn.commit()

    def bump_attempt(self, url: str):
        with self._lock:
            self._conn.execute("UPDATE urls SET attempts=attempts+1 WHERE url=?", (url,))
            self._conn.commit()

    def set_robots(self, url: str, verdict: str):
        with self._lock:
            self._conn.execute("UPDATE urls SET robots=?, state=? WHERE url=?",
                               (verdict, "disallowed" if verdict == "disallow" else "queued", url))
            self._conn.commit()

    def get(self, url: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM urls WHERE url=?", (url,)).fetchone()
        return dict(r) if r else None

    def stats(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT state, COUNT(*) c FROM urls GROUP BY state").fetchall()
            return {r["state"]: r["c"] for r in rows}

    # ---------- raw html cache ----------
    def put_html(self, url: str, html: str):
        with self._lock:
            self._conn.execute(
                "INSERT INTO raw_html (url, html) VALUES (?,?) "
                "ON CONFLICT(url) DO UPDATE SET html=excluded.html", (url, html))
            self._conn.commit()

    def get_html(self, url: str) -> str | None:
        r = self._conn.execute("SELECT html FROM raw_html WHERE url=?", (url,)).fetchone()
        return r["html"] if r else None

    # ---------- parsed entries ----------
    def upsert_entry(self, e: CatalogEntry, source_url: str) -> str:
        """Returns 'inserted' or 'merged'. Dedupes by fingerprint OR normalized
        designation, so re-scans merge into the existing entry instead of
        creating duplicates."""
        fp = e.fingerprint()
        dk = e.designation_key()
        with self._lock:
            existing = self._conn.execute(
                "SELECT data FROM entries WHERE fingerprint=? OR designation_key=? "
                "OR LOWER(designation)=?",
                (fp, dk, dk)).fetchone()
            if existing:
                old = json.loads(existing["data"])
                src_urls = {s["url"] for s in old.get("sources", [])}
                for s in e.sources:
                    if s.url not in src_urls:
                        old.setdefault("sources", []).append(s.to_dict())
                        src_urls.add(s.url)
                old["fetched_at"] = e.fetched_at or old.get("fetched_at", "")
                if len(e.specs) > len(old.get("specs", [])):
                    old["specs"] = e.specs
                self._conn.execute(
                    "UPDATE entries SET data=?, source_url=?, category=?, designation_key=? "
                    "WHERE fingerprint=? OR designation_key=? OR LOWER(designation)=?",
                    (json.dumps(old, ensure_ascii=False), source_url, e.category, dk,
                     fp, dk, dk))
                self._conn.commit()
                return "merged"
            self._conn.execute(
                "INSERT INTO entries (fingerprint, designation, designation_key, category, data, source_url, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (fp, e.designation, dk, e.category, entry_to_json(e), source_url, now_iso()))
            self._conn.commit()
            return "inserted"

    def link_parsed(self, url: str, e: CatalogEntry | None, json_blob: str | None = None):
        with self._lock:
            self._conn.execute("UPDATE urls SET parsed=? WHERE url=?",
                               (json_blob if json_blob is not None
                                else (entry_to_json(e) if e else None), url))
            self._conn.commit()

    def all_entries(self) -> list[CatalogEntry]:
        rows = self._conn.execute("SELECT data FROM entries").fetchall()
        return [CatalogEntry.from_dict(json.loads(r["data"])) for r in rows]

    def entry_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]

    def close(self):
        with self._lock:
            self._conn.commit()
            self._conn.close()
