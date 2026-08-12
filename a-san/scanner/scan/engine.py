"""Orchestrator: seed -> discover -> crawl -> parse -> dedupe -> export.

Pipeline (idempotent + resumable):
  seed    load existing catalog + optional seeds file into the queue (as done/queued)
  discover  sitemap enumeration of product URLs for the wanted categories
  crawl   fetch + parse + upsert, honouring robots.txt, cache and politeness
  export  write catalog-data.json in the A-SAN v1.0 schema
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, CATEGORY_KEYS
from .models import CatalogEntry, SourceRef
from .net import HttpFetcher, RobotsGate
from .parsers import parse_armyrecognition, parse_patent, parse_news_article
from .parsers_weaponsystems import parse_weaponsystem
from .parsers_militaryfactory import parse_militaryfactory_detail
from .sitemap import product_urls_from_sitemap, article_urls_from_sitemap, sitemap_urls_to_parse
from .store import ScanStore

log = logging.getLogger("scan")

ARMYREC_HOST = "www.armyrecognition.com"
PATENTS_HOST = "patents.google.com"
WEAPONSYSTEMS_HOST = "weaponsystems.net"
MILITARYFACTORY_HOST = "www.militaryfactory.com"


def load_catalog_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for entries in (d.get("entries") or {}).values():
        out.extend(entries)
    return out


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ScanStore(settings.db_path)
        self.robots = RobotsGate(settings.user_agent)
        self.fetchers: dict[str, HttpFetcher] = {}
        self._seeded = False

    def _fetcher(self, host: str) -> HttpFetcher:
        if host not in self.fetchers:
            self.fetchers[host] = HttpFetcher(self.settings, self.robots)
        return self.fetchers[host]

    # ---------------- seeding ----------------
    def seed_from_catalog(self):
        """Load existing catalog entries so they are not re-created (dedupe)."""
        for e in load_catalog_entries(self.settings.catalog_path):
            try:
                entry = CatalogEntry.from_dict(e)
            except Exception:
                continue
            src = entry.sources[0].url if entry.sources else ""
            self.store.upsert_entry(entry, src)
        n = self.store.entry_count()
        log.info("seeded catalog: %d existing entries in scan store", n)

    def seed_urls(self, urls: list[str], kind: str = "product"):
        for u in urls:
            host = u.split("/")[2]
            self.store.enqueue(u, host, kind=kind)
        log.info("seeded %d urls", len(urls))

    def seed_file(self):
        p = self.settings.seeds_path
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        count = 0
        for cat_key, urls in (data.get("seeds") or {}).items():
            disp = CATEGORY_KEYS.get(cat_key, cat_key)
            for u in urls:
                host = u.split("/")[2]
                self.store.enqueue(u, host, category=disp, kind="product")
                count += 1
        log.info("seeded %d urls from %s", count, p)

    # ---------------- discovery ----------------
    def discover(self, wanted_keys: set[str]):
        if not self.settings.obey_robots:
            log.warning("obey_robots is OFF — aborting discovery (hard rule).")
            sys.exit("Refusing to run with obey_robots=False unless the site "
                     "operator explicitly whitelists the scanner UA (see POLICY.md).")
        xml = None
        for url in sitemap_urls_to_parse():
            res = self._fetcher(ARMYREC_HOST).fetch(url, store=self.store, use_cache=True)
            if res.status == 200 and res.html:
                xml = res.html
                break
        if not xml:
            log.warning("sitemap unreachable; continuing with seeds only")
            return 0
        urls = product_urls_from_sitemap(xml, wanted_keys)
        added = 0
        for u, key, disp in urls:
            added += self.store.enqueue(u, ARMYREC_HOST, category=disp, kind="product")
        arts = article_urls_from_sitemap(xml, wanted_keys)
        for u, key, disp in arts:
            added += self.store.enqueue(u, ARMYREC_HOST, category=disp, kind="article")
        log.info("discovery: %d product + %d article urls enqueued (of %d candidates)",
                 added - len(arts), len(arts), len(urls) + len(arts))
        return added

    # ---------------- crawl ----------------
    def crawl(self, wanted_display: list[str], limit: int | None = None):
        fetch_limit = limit or self.settings.limit
        done_fetch = 0
        while True:
            batch = self.store.next_batch(10, categories=wanted_display)
            if not batch:
                break
            if fetch_limit is not None and done_fetch >= fetch_limit:
                # requeue the leftover? leave them queued for the next run
                break
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.settings.max_workers) as pool:
                futs = {pool.submit(self._process, row): row for row in batch}
                for fut in concurrent.futures.as_completed(futs):
                    row = futs[fut]
                    try:
                        fut.result()
                    except Exception as e:
                        log.error("row %s failed: %s", row["url"], e)
                        self.store.mark(row["url"], "failed", error=str(e)[:500])
            done_fetch += len(batch)

    def _process(self, row: dict):
        url = row["url"]
        host = row["domain"]
        kind = row["kind"] or "product"
        fetched = self._fetcher(host).fetch(url, store=self.store,
                                            use_cache=self.settings.use_cache)
        if fetched.robots_verdict == "disallow":
            self.store.set_robots(url, "disallow")
            return
        if fetched.status == 200 and fetched.html:
            if host == PATENTS_HOST and "/patent/" in url:
                disp = row["category"] or "Uncategorized"
                pub = url.rstrip("/").rsplit("/", 1)[-1]
                e = parse_patent(url, fetched.html, disp, system_designation=pub,
                                 auto_classify=True)
                if e:
                    op = self.store.upsert_entry(e, url)
                    self.store.link_parsed(url, e)
                    self.store.mark(url, "done", status=200)
                    log.info("[%s] %s -> %s (patent)", disp, e.designation[:50], op)
                    return
            elif host == ARMYREC_HOST and kind == "article":
                disp = row["category"] or "Uncategorized"
                e = parse_news_article(url, fetched.html, disp)
                if e:
                    op = self.store.upsert_entry(e, url)
                    self.store.link_parsed(url, e)
                    self.store.mark(url, "done", status=200)
                    log.info("[%s] %s -> %s (news)", disp, e.designation[:50], op)
                    return
            elif host == ARMYREC_HOST and kind == "product":
                disp = row["category"] or "Uncategorized"
                e = parse_armyrecognition(url, fetched.html, disp)
                if e:
                    op = self.store.upsert_entry(e, url)
                    self.store.link_parsed(url, e)
                    self.store.mark(url, "done", status=200)
                    log.info("[%s] %s -> %s (%s)", disp, e.designation[:50], op, len(e.specs))
                    return
            elif host == WEAPONSYSTEMS_HOST and "/system/" in url:
                disp = row["category"] or "Uncategorized"
                e = parse_weaponsystem(url, fetched.html, disp)
                if e:
                    op = self.store.upsert_entry(e, url)
                    self.store.link_parsed(url, e)
                    self.store.mark(url, "done", status=200)
                    log.info("[%s] %s -> %s (%s)", disp, e.designation[:50], op, len(e.specs))
                    return
            elif host == MILITARYFACTORY_HOST and "detail.php?aircraft_id=" in url:
                e = parse_militaryfactory_detail(url, fetched.html)
                if e:
                    op = self.store.upsert_entry(e, url)
                    self.store.link_parsed(url, e)
                    self.store.mark(url, "done", status=200)
                    log.info("[%s] %s -> %s (%s)", e.category, e.designation[:50], op, len(e.specs))
                    return
            # unknown host/kind or parser returned None: still mark fetched so the
            # page isn't re-fetched on every run (no data extracted).
            self.store.mark(url, "done", status=200)
            return
        if fetched.status == 0:
            self.store.mark(url, "failed", error="network/status 0")
        else:
            self.store.mark(url, "done", status=fetched.status)

    # ---------------- export ----------------
    def export(self):
        entries = self.store.all_entries()
        grouped = {k: [] for k in CATEGORY_KEYS}
        for e in entries:
            key = None
            for k, disp in CATEGORY_KEYS.items():
                if disp.lower() == (e.category or "").lower():
                    key = k
                    break
            if key is None:
                key = "uncategorized"
            grouped.setdefault(key, []).append(e)
        # stable order within category
        for key in grouped:
            grouped[key].sort(key=lambda e: e.designation.lower())
        catalog = {
            "schema_version": "1.0",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source_policy": {
                "allowed_sources": [
                    "https://www.armyrecognition.com",
                    "https://patents.google.com",
                    "https://ppubs.uspto.gov",
                    "https://worldwide.espacenet.com",
                    "https://janes.com",
                    "https://www.militaryfactory.com",
                ],
                "note": ("Compiled by the A-SAN deep scanner. robots.txt and site ToS are "
                         "respected; every entry carries the exact source URL it was fetched "
                         "from; only data printed on the source page is included."),
            },
            "categories": [CATEGORY_KEYS[k] for k in CATEGORY_KEYS],
            "category_keys": list(CATEGORY_KEYS.keys()),
            "entries": {k: [e.to_dict() for e in v] for k, v in grouped.items()},
            "entry_counts": {k: len(v) for k, v in grouped.items()},
            "total_entries": sum(len(v) for v in grouped.values()),
        }
        self.settings.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings.catalog_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.settings.catalog_path)
        log.info("exported %d entries to %s", catalog["total_entries"], self.settings.catalog_path)

    # ---------------- web export ----------------
    def export_web(self, out_dir: Path):
        """Write the static web bundle: per-category data JSONs + category.html.

        category.html is a static template (scanner/web/category.html) that reads
        ./data/categories.json and ./data/<category-key>.json and renders the
        cards client-side — so it scales to thousands of entries without extra
        HTML files.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        data_dir = out_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        entries = self.store.all_entries()
        grouped: dict[str, list[CatalogEntry]] = {}
        for e in entries:
            key = None
            for k, disp in CATEGORY_KEYS.items():
                if disp.lower() == (e.category or "").lower():
                    key = k
                    break
            grouped.setdefault(key or "uncategorized", []).append(e)

        cats = []
        for key in CATEGORY_KEYS:
            lst = sorted(grouped.get(key, []), key=lambda e: e.designation.lower())
            cats.append({"key": key, "name": CATEGORY_KEYS[key], "count": len(lst)})
            (data_dir / f"{key}.json").write_text(
                json.dumps({"key": key, "category": CATEGORY_KEYS[key],
                            "count": len(lst), "entries": [e.to_dict() for e in lst]},
                           ensure_ascii=False), encoding="utf-8")

        # picklist (scores) when available — powers the score badges in the UI
        pl = self.settings.root / "data" / "picklist.json"
        picklist_present = False
        if pl.exists():
            try:
                shutil.copy(pl, data_dir / "picklist.json")
                picklist_present = True
            except OSError:
                picklist_present = False

        meta = {
            "schema_version": "web.1",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_entries": sum(c["count"] for c in cats),
            "picklist_present": picklist_present,
            "categories": cats,
        }
        (data_dir / "categories.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        tpl = Path(__file__).resolve().parent.parent / "web" / "templates" / "category.html"
        if tpl.exists():
            shutil.copy(tpl, out_dir / "category.html")
        log.info("web export: %d entries, %d categories -> %s",
                 meta["total_entries"], len(cats), out_dir)

    def status(self) -> dict:
        st = self.store.stats()
        return {"queue": st, "entries": self.store.entry_count()}

    def close(self):
        self.store.close()
