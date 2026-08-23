"""SQLite-backed scan store: resumable queue, HTTP cache, parsed entries, catalog merge.

Thread-safety: one writer connection guarded by a lock; readers use a separate
read-only connection when needed. All writes are small and serialised.
"""

from __future__ import annotations

import json
import re
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

    def next_batch(self, limit: int, categories: list[str] | None = None,
                   domains: list[str] | None = None) -> list[dict]:
        with self._lock:
            conds, params = ["state='queued'"], []
            if categories:
                ph = ",".join("?" * len(categories))
                conds.append(f"(category IN ({ph}) OR category IS NULL)")
                params.extend(categories)
            if domains:
                ph = ",".join("?" * len(domains))
                conds.append(f"domain IN ({ph})")
                params.extend(domains)
            rows = self._conn.execute(
                f"SELECT * FROM urls WHERE {' AND '.join(conds)} "
                "ORDER BY rowid LIMIT ?", (*params, limit)).fetchall()
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
                "SELECT fingerprint, data FROM entries WHERE fingerprint=? OR designation_key=? "
                "OR LOWER(designation)=?",
                (fp, dk, dk)).fetchone()
            if not existing:
                try:
                    self._conn.execute(
                        "INSERT INTO entries (fingerprint, designation, designation_key, category, data, source_url, created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (fp, e.designation, dk, e.category, entry_to_json(e), source_url, now_iso()))
                    self._conn.commit()
                    return "inserted"
                except sqlite3.IntegrityError:
                    # Collision via a differently-styled designation_key on a
                    # legacy row (e.g. 'lav-25' vs normalized 'lav 25'): merge
                    # into whichever row owns this key now.
                    self._conn.rollback()
                    existing = self._conn.execute(
                        "SELECT fingerprint, data FROM entries WHERE designation_key=?",
                        (dk,)).fetchone()
                    if not existing:
                        raise
            # Merge strictly into the ONE matched row — never a broad UPDATE,
            # or punctuation-twin rows would collide on designation_key.
            target_fp = existing["fingerprint"]
            old = json.loads(existing["data"])
            src_urls = {s["url"] for s in old.get("sources", [])}
            for s in e.sources:
                if s.url not in src_urls:
                    old.setdefault("sources", []).append(s.to_dict())
                    src_urls.add(s.url)
            old["fetched_at"] = e.fetched_at or old.get("fetched_at", "")
            if len(e.specs) > len(old.get("specs", [])):
                old["specs"] = e.specs
            # Category: never downgrade a specific category to a vaguer
            # one on merge (e.g. a news parser passing 'Uncategorized'
            # must not clobber 'Armored vehicles and equipment').
            new_cat = (e.category or "").strip()
            old_cat = (old.get("category") or "").strip()
            if new_cat and new_cat != "Uncategorized" and \
                    (not old_cat or old_cat == "Uncategorized"):
                old["category"] = new_cat
            # Two distinct rows can converge on the same normalized key (e.g.
            # 'LAV-25' and 'LAV 25' seeded side by side). Fold the twin into
            # the surviving record instead of violating the unique index.
            twin = self._conn.execute(
                "SELECT fingerprint, data FROM entries WHERE designation_key=? AND fingerprint<>?",
                (dk, target_fp)).fetchone()
            if twin:
                tdata = json.loads(twin["data"])
                keep, other = ((tdata, old) if
                               len(tdata.get("specs", [])) >= len(old.get("specs", []))
                               else (old, tdata))
                keep_fp = twin["fingerprint"] if keep is tdata else target_fp
                drop_fp = target_fp if keep_fp == twin["fingerprint"] \
                    else twin["fingerprint"]
                urls = {s["url"] for s in keep.get("sources", [])}
                for s_x in other.get("sources", []):
                    if s_x["url"] not in urls:
                        keep.setdefault("sources", []).append(s_x)
                        urls.add(s_x["url"])
                if len(other.get("specs", [])) > len(keep.get("specs", [])):
                    keep["specs"] = other["specs"]
                kc = (keep.get("category") or "").strip()
                oc = (other.get("category") or "").strip()
                if oc and oc != "Uncategorized" and (not kc or kc == "Uncategorized"):
                    keep["category"] = oc
                # free the key first — SQLite validates uniqueness per statement
                self._conn.execute("DELETE FROM entries WHERE fingerprint=?",
                                   (drop_fp,))
                self._conn.execute(
                    "UPDATE entries SET data=?, designation_key=?, source_url=? WHERE fingerprint=?",
                    (json.dumps(keep, ensure_ascii=False), dk, source_url, keep_fp))
                self._conn.commit()
                return "merged"
            self._conn.execute(
                "UPDATE entries SET data=?, source_url=?, designation_key=?, category=? "
                "WHERE fingerprint=?",
                (json.dumps(old, ensure_ascii=False), source_url, dk,
                 old["category"], target_fp))
            self._conn.commit()
            return "merged"

    def link_parsed(self, url: str, e: CatalogEntry | None, json_blob: str | None = None):
        with self._lock:
            self._conn.execute("UPDATE urls SET parsed=? WHERE url=?",
                               (json_blob if json_blob is not None
                                else (entry_to_json(e) if e else None), url))
            self._conn.commit()

    def all_entries(self) -> list[CatalogEntry]:
        rows = self._conn.execute("SELECT data FROM entries").fetchall()
        return [CatalogEntry.from_dict(json.loads(r["data"])) for r in rows]

    def raw_entries(self) -> list[dict]:
        """Fingerprint + designation + category + parsed data for quality passes."""
        rows = self._conn.execute(
            "SELECT fingerprint, designation, category, data FROM entries").fetchall()
        out = []
        for r in rows:
            try:
                d = json.loads(r["data"])
            except Exception:
                continue
            out.append({"fingerprint": r["fingerprint"],
                        "designation": r["designation"] or "",
                        "category": r["category"] or "",
                        "data": d})
        return out

    def set_category(self, fingerprint: str, category: str):
        with self._lock:
            self._conn.execute("UPDATE entries SET category=?, data=? WHERE fingerprint=?",
                               (category,
                                json.dumps({**json.loads(
                                    self._conn.execute(
                                        "SELECT data FROM entries WHERE fingerprint=?",
                                        (fingerprint,)).fetchone()["data"]),
                                    "category": category}, ensure_ascii=False),
                                fingerprint))
            self._conn.commit()

    def rebuild_designation_keys(self) -> int:
        """Recompute designation_key for every entry with the current
        normalization and merge punctuation-variant duplicates. Returns the
        number of duplicate rows merged away. Run while no crawl is writing."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT fingerprint, designation, data FROM entries").fetchall()
            groups: dict[str, list[sqlite3.Row]] = {}
            for r in rows:
                dk = " ".join(re.sub(r"[^a-z0-9]+", " ",
                                     (r["designation"] or "").lower()).split()).strip()
                groups.setdefault(dk, []).append(r)

            merged = 0
            for dk, group in groups.items():
                if len(group) < 2:
                    continue
                # keep the row with the richest spec set as primary
                def richness(r):
                    try:
                        return len(json.loads(r["data"]).get("specs", []))
                    except Exception:
                        return 0
                group = sorted(group, key=richness, reverse=True)
                keep = group[0]
                keep_data = json.loads(keep["data"])
                for other in group[1:]:
                    od = json.loads(other["data"])
                    urls = {s["url"] for s in keep_data.get("sources", [])}
                    for s in od.get("sources", []):
                        if s["url"] not in urls:
                            keep_data.setdefault("sources", []).append(s)
                            urls.add(s["url"])
                    if len(od.get("specs", [])) > len(keep_data.get("specs", [])):
                        keep_data["specs"] = od["specs"]
                    if not (keep_data.get("category") or "").strip() \
                            and (od.get("category") or "").strip():
                        keep_data["category"] = od["category"]
                    self._conn.execute(
                        "DELETE FROM entries WHERE fingerprint=?",
                        (other["fingerprint"],))
                    merged += 1
                self._conn.execute(
                    "UPDATE entries SET data=?, designation_key=? WHERE fingerprint=?",
                    (json.dumps(keep_data, ensure_ascii=False), dk,
                     keep["fingerprint"]))
            # normalize keys for singleton groups too
            for dk, group in groups.items():
                if len(group) == 1:
                    r = group[0]
                    self._conn.execute(
                        "UPDATE entries SET designation_key=? WHERE fingerprint=?",
                        (dk, r["fingerprint"]))
            self._conn.commit()
            return merged

    def entry_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]

    def close(self):
        with self._lock:
            self._conn.commit()
            self._conn.close()
