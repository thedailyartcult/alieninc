"""CLI for the A-SAN deep scanner.

Commands:
  seed       load existing catalog + seeds file into the scan store
  discover   pull the sitemap and enqueue category-mapped product URLs
  crawl      process the queued product URLs (resumable)
  run        seed + discover + crawl + export (the full cycle)
  export     write catalog-data.json from the scan store
  status     queue/entry summary
  import-janes  ingest a research-desk CSV (licensed Janes data)

Examples:
  python -m scan run --categories aircraft,uavs --limit 25
  python -m scan run                        # deep, full run
  python -m scan crawl --resume
  python -m scan discover
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import Settings, CATEGORY_KEYS, category_key
from .engine import Engine
from .models import CatalogEntry, SourceRef, now_iso
from .parsers import janes_import_csv
from .parsers_militaryfactory import parse_militaryfactory_country, build_entries, parse_militaryfactory_detail
from .parsers_designation import parse_designation_listing
from .parsers_missilethreat import parse_missilethreat_listing
from .parsers_modernfirearms import parse_modernfirearms_listing, MODERNFIREARMS_SEED_URLS
from .picklist import CurationRules, curate, write_outputs
from .patent_feed import feed_patents, feed_from_file


def _settings(args) -> Settings:
    s = Settings(
        min_delay_seconds=args.delay,
        max_workers=args.workers,
        max_retries=args.retries,
        refresh=args.refresh,
        limit=args.limit,
        obey_robots=not args.no_robots,
        espacenet_ops_key=os.environ.get("ESPACENET_OPS_KEY", ""),
        espacenet_ops_secret=os.environ.get("ESPACENET_OPS_SECRET", ""),
        uspto_odp_token=os.environ.get("USPTO_ODP_TOKEN", ""),
    )
    if args.catalog:
        s.catalog_path = Path(args.catalog)
    if args.db:
        s.db_path = Path(args.db)
    if args.seeds:
        s.seeds_path = Path(args.seeds)
    return s


def _categories(args) -> list[str]:
    if not args.categories:
        return list(CATEGORY_KEYS.values())
    out = []
    for c in args.categories.split(","):
        c = c.strip()
        if not c:
            continue
        key = c if c in CATEGORY_KEYS else category_key(c)
        out.append(CATEGORY_KEYS[key])
    return out


def cmd_seed(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    eng.seed_file()
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_discover(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    wanted = set(category_key(c) for c in _categories(args))
    added = eng.discover(wanted)
    print(f"discovered/enqueued: {added}")
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_crawl(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    eng.crawl(_categories(args), limit=args.limit)
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_run(args, s: Settings):
    eng = Engine(s)
    eng.seed_from_catalog()
    eng.seed_file()
    wanted = set(category_key(c) for c in _categories(args))
    eng.discover(wanted)
    eng.crawl(_categories(args), limit=args.limit)
    eng.export()
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_discover_sources(args, s: Settings):
    """Enumerate the catalog listing pages of the three fact-extraction sources
    (designation-systems.net, missilethreat.csis.org, modernfirearms.net) and
    enqueue every detail URL into the scan store. robots.txt-gated, polite,
    cached. Run this once per source to populate the queue, then `crawl`."""
    eng = Engine(s)
    eng.seed_from_catalog()
    summary: dict[str, int] = {}

    # --- designation-systems.net: /usmilav/missiles.html catalog table ---
    ds_listing_url = "https://www.designation-systems.net/usmilav/missiles.html"
    res = eng._fetcher("www.designation-systems.net").fetch(
        ds_listing_url, store=eng.store, use_cache=True)
    n_ds = 0
    if res.status == 200 and res.html:
        for url, _desig, _mfr in parse_designation_listing(res.html, ds_listing_url):
            n_ds += eng.store.enqueue(
                url, "www.designation-systems.net", kind="product")
    summary["designation-systems.net"] = n_ds

    # --- missilethreat.csis.org: /missile/ dropdown (full catalog) ---
    mt_listing_url = "https://missilethreat.csis.org/missile/"
    res = eng._fetcher("missilethreat.csis.org").fetch(
        mt_listing_url, store=eng.store, use_cache=True)
    n_mt = 0
    if res.status == 200 and res.html:
        for url, _name in parse_missilethreat_listing(res.html):
            n_mt += eng.store.enqueue(
                url, "missilethreat.csis.org", kind="product")
    summary["missilethreat.csis.org"] = n_mt

    # --- modernfirearms.net: each working category index page ---
    n_mf = 0
    for _mf_cat, idx_url in MODERNFIREARMS_SEED_URLS.items():
        res = eng._fetcher("modernfirearms.net").fetch(
            idx_url, store=eng.store, use_cache=True)
        if res.status == 200 and res.html:
            for url, _name, _excerpt in parse_modernfirearms_listing(res.html):
                n_mf += eng.store.enqueue(
                    url, "modernfirearms.net", kind="product")
    summary["modernfirearms.net"] = n_mf

    print(json.dumps({
        "enqueued_by_source": summary,
        "total_enqueued": sum(summary.values()),
        "status": eng.status(),
        "next": "python -m scan crawl --categories air-launched-munitions,sea-launched-cruise-missiles,rocket-and-missile-weapons,small-arms",
    }, indent=2))
    eng.close()


def cmd_export(args, s: Settings):
    eng = Engine(s)
    eng.export()
    eng.close()


def cmd_status(args, s: Settings):
    eng = Engine(s)
    print(json.dumps(eng.status(), indent=2))
    eng.close()


def cmd_import_military(args, s: Settings):
    """Ingest the operator-scraped militaryfactory.com by-country pages
    (scanner/data/military/*.html) into the scan store. Rows are merged by the
    stable aircraft_id so the same aircraft listed under several countries
    accumulates its operators; clearly civilian-only types are dropped."""
    eng = Engine(s)
    src_dir = Path(args.military_dir)
    if not src_dir.is_absolute():
        src_dir = s.root / src_dir
    if not src_dir.exists():
        print(f"military data dir not found: {src_dir}")
        eng.close()
        return
    merged: dict[int, dict] = {}
    for p in sorted(src_dir.glob("*.html")):
        country = p.stem.replace("militaryfactory", "").upper()
        rows = parse_militaryfactory_country(
            p.read_text(encoding="utf-8", errors="replace"), country)
        for r in rows:
            aid = r["aircraft_id"]
            if aid in merged:
                merged[aid]["operators"] |= r["operators"]
            else:
                merged[aid] = r
    entries = build_entries(list(merged.values()))
    ops = {"inserted": 0, "merged": 0}
    for e in entries:
        ops[eng.store.upsert_entry(e, e.sources[0].url if e.sources else "")] += 1
    # Enqueue the per-aircraft detail pages so the crawler can enrich the
    # entries with full specs. Each detail URL is unique per aircraft_id.
    enqueued = 0
    for u, cat in {e.sources[0].url: e.category for e in entries if e.sources}.items():
        enqueued += eng.store.enqueue(u, "www.militaryfactory.com", category=cat, kind="product")
    print(json.dumps({
        "files_parsed": len(list(src_dir.glob("*.html"))),
        "unique_aircraft": len(merged),
        "entries_upserted": len(entries),
        "inserted": ops["inserted"],
        "merged": ops["merged"],
        "dropped_civilian": len(merged) - len(entries),
        "detail_urls_enqueued": enqueued,
        "next": "python -m scan crawl --categories aircraft,uavs --delay 1",
    }, indent=2))
    eng.close()


def cmd_re_enrich_military(args, s: Settings):
    """Re-parse the cached militaryfactory detail HTML (already fetched) with
    the latest parser and re-upsert, so enriched specs (Mission Roles, etc.)
    fold into the existing entries. No network needed."""
    eng = Engine(s)
    rows = eng.store._conn.execute(
        "SELECT url, html FROM raw_html WHERE url LIKE "
        "'https://www.militaryfactory.com/aircraft/detail.php?aircraft_id=%'").fetchall()
    ops = {"inserted": 0, "merged": 0, "skipped": 0}
    for row in rows:
        e = parse_militaryfactory_detail(row["url"], row["html"])
        if e is None:
            ops["skipped"] += 1
            continue
        ops[eng.store.upsert_entry(e, row["url"])] += 1
    print(json.dumps({
        "cached_detail_pages": len(rows),
        "re_upserted": ops["inserted"] + ops["merged"],
        "inserted": ops["inserted"],
        "merged": ops["merged"],
        "skipped": ops["skipped"],
        "next": "python -m scan export && python -m scan build-web && python -m scan curate",
    }, indent=2))
    eng.close()


def cmd_import_janes(args, s: Settings):
    rows = janes_import_csv(args.csv)
    print(f"imported {len(rows)} Janes rows (research-desk licensed data); "
          f"review manually before merge.")
    for r in rows[:5]:
        print("  -", r.get("designation", ""), "|", r.get("category", ""))


def cmd_curate(args, s: Settings):
    eng = Engine(s)
    rules = CurationRules(
        min_score=args.min_score,
        max_per_category=args.max_per_category,
        max_total=args.max_total,
    )
    report = curate(eng.store.all_entries(), rules)
    write_outputs(report, s.root / "data")
    print(json.dumps({
        "raw_pool_size": report["raw_pool_size"],
        "after_filters_size": report["after_filters_size"],
        "picklist_size": report["picklist_size"],
        "excluded_counts": report["excluded_counts"],
        "rules": report["rules"],
    }, indent=2))
    print(f"wrote data/picklist.json + data/picklist.csv (schema {report['picklist_schema_version']})")
    eng.close()


def cmd_build_web(args, s: Settings):
    eng = Engine(s)
    # Default: the A-SAN site root (repo root, sibling of index.html) so
    # https://a-san.alieninc.tech/category.html serves the catalog. Override
    # with --out to stage elsewhere.
    default_out = s.root.parent
    out = Path(args.out) if args.out else default_out
    if not out.is_absolute():
        out = s.root.parent / out
    eng.export_web(out)
    eng.close()
    print(json.dumps({
        "out": str(out),
        "note": "serve with:  python3 -m http.server 8000 --directory %s" % out,
        "deployed": "https://a-san.alieninc.tech/category.html",
    }, indent=2))


def cmd_patent_feed(args, s: Settings):
    """Enqueue patent publication numbers as Google-Patents reader URLs.

    Either `--patents-file list.txt` (one pub number per line) or, with no file,
    a live API query (USPTO Open Data Portal bearer token, or Espacenet OPS
    key/secret — whichever is configured in the env). Each resulting
    publication number becomes a `patents.google.com/patent/<pub>` URL and is
    enqueued under `--category`. Then run `python -m scan crawl`.
    """
    eng = Engine(s)
    cat = args.category
    category_display = _categories(argparse.Namespace(categories=cat))[0] if cat else "Uncategorized"
    try:
        if args.patents_file:
            count = feed_from_file(eng, args.patents_file, category_display, limit=args.limit)
        else:
            count = feed_patents(eng, args.query, category_display,
                                 limit=args.limit, per_page=args.per_page,
                                 max_pages=args.max_pages)
    finally:
        eng.close()
    print(json.dumps({
        "enqueued": count,
        "category": category_display,
        "query": args.query,
        "next": "python -m scan crawl",
    }, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m scan", description="A-SAN deep scanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("run", "crawl", "discover", "seed", "export", "status"):
        sp = sub.add_parser(name)
        _add_common(sp)
    cp = sub.add_parser("curate")
    cp.add_argument("--min-score", type=float, default=40.0)
    cp.add_argument("--max-per-category", type=int, default=15)
    cp.add_argument("--max-total", type=int, default=100)
    _add_common(cp)
    wp = sub.add_parser("build-web")
    wp.add_argument("--out", default=None, help="output dir (default <scanner>/web)")
    _add_common(wp)
    fp = sub.add_parser("patent-feed", help="enqueue patent pub-numbers as google-patents URLs")
    fp.add_argument("--query", default="guided missile defense", help="search text for the API feed")
    fp.add_argument("--category", default="Rocket and missile weapons", help="category to assign (key or display name)")
    fp.add_argument("--patents-file", default=None, help="txt list of pub numbers (one per line) instead of an API query")
    fp.add_argument("--per-page", type=int, default=50, help="results per API page")
    fp.add_argument("--max-pages", type=int, default=20, help="max API pages to pull")
    _add_common(fp)
    sp = sub.add_parser("import-janes")
    sp.add_argument("csv")
    _add_common(sp)
    rp = sub.add_parser("import-military",
                        help="ingest operator-scraped militaryfactory.com by-country pages")
    rp.add_argument("--military-dir", default="data/military",
                    help="dir containing militaryfactory<COUNTRY>.html pages")
    _add_common(rp)
    rep = sub.add_parser("re-enrich-military",
                         help="re-parse cached militaryfactory detail HTML and re-upsert")
    _add_common(rep)
    dsp = sub.add_parser("discover-sources",
                         help="enumerate listing pages of designation-systems.net, "
                              "missilethreat.csis.org, modernfirearms.net and enqueue "
                              "their detail URLs")
    _add_common(dsp)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if not args.quiet else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    s = _settings(args)
    if args.cmd == "seed":
        cmd_seed(args, s)
    elif args.cmd == "discover":
        cmd_discover(args, s)
    elif args.cmd == "crawl":
        cmd_crawl(args, s)
    elif args.cmd == "run":
        cmd_run(args, s)
    elif args.cmd == "export":
        cmd_export(args, s)
    elif args.cmd == "status":
        cmd_status(args, s)
    elif args.cmd == "import-janes":
        cmd_import_janes(args, s)
    elif args.cmd == "import-military":
        cmd_import_military(args, s)
    elif args.cmd == "re-enrich-military":
        cmd_re_enrich_military(args, s)
    elif args.cmd == "discover-sources":
        cmd_discover_sources(args, s)
    elif args.cmd == "curate":
        cmd_curate(args, s)
    elif args.cmd == "build-web":
        cmd_build_web(args, s)
    elif args.cmd == "patent-feed":
        cmd_patent_feed(args, s)


def _add_common(sp):
    sp.add_argument("--categories", help="comma-separated keys or names, e.g. aircraft,uavs")
    sp.add_argument("--limit", type=int, default=None, help="cap product pages this run")
    sp.add_argument("--delay", type=float, default=1.5, help="min seconds between requests/host")
    sp.add_argument("--workers", type=int, default=1, help="parallel hosts (politeness kept per host)")
    sp.add_argument("--retries", type=int, default=3)
    sp.add_argument("--refresh", action="store_true", help="ignore the raw-HTML cache")
    sp.add_argument("--no-robots", action="store_true",
                    help="FORBIDDEN unless site ops whitelisted the scanner UA (see POLICY.md)")
    sp.add_argument("--catalog", help="output catalog path")
    sp.add_argument("--db", help="scan store path")
    sp.add_argument("--seeds", help="seeds json path")
    sp.add_argument("-q", "--quiet", action="store_true")


if __name__ == "__main__":
    sys.exit(main())
