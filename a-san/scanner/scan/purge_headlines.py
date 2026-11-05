"""One-off purge of news-headline designations from the scan store.

Removes rows whose designation is really an article/blog title (Defense
Express, Covert Shores, Army Recognition articles, ...) so Panteon never
sees headlines as weapon systems. The ingest gate in engine.Engine._admit
blocks new ones; this script clears existing pollution.

Usage:
    python3 -m scan.purge_headlines            # dry run: report only
    python3 -m scan.purge_headlines --apply    # delete + vacuum

Afterwards refresh outputs:
    cd scanner && python3 -m scan export && python3 -m scan build-web
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from .sanity import looks_like_news_headline

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scan.db"


def headline_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT fingerprint, designation, category, data FROM entries"
    ).fetchall()
    hits = []
    for fp, dg, cat, data in rows:
        if looks_like_news_headline(dg):
            try:
                blob = json.loads(data)
            except Exception:
                blob = {}
            labels = sorted({s.get("label", "?")
                             for s in (blob.get("sources") or [])})
            hits.append({"fingerprint": fp, "designation": dg,
                         "category": cat, "sources": ", ".join(labels)})
    return hits


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    hits = headline_rows(conn)
    by_src = Counter(h["sources"].split(", ")[0] for h in hits)
    by_cat = Counter(h["category"] for h in hits)
    total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    print(f"store: {total} entries | headline-like: {len(hits)}")
    print("by source:", dict(by_src.most_common()))
    print("by category:", dict(by_cat.most_common()))
    for h in hits[:15]:
        print(f"  - [{h['category']}] {h['designation'][:80]}")
    if len(hits) > 15:
        print(f"  ... and {len(hits) - 15} more")
    if not apply:
        print("\ndry run — re-run with --apply to delete")
        return 0
    fps = [h["fingerprint"] for h in hits]
    conn.executemany("DELETE FROM entries WHERE fingerprint=?",
                     [(fp,) for fp in fps])
    conn.commit()
    conn.execute("VACUUM")
    left = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    print(f"\ndeleted {len(fps)} entries; store now {left}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
