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
from .parsers import janes_import_csv
from .picklist import CurationRules, curate, write_outputs


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


def cmd_export(args, s: Settings):
    eng = Engine(s)
    eng.export()
    eng.close()


def cmd_status(args, s: Settings):
    eng = Engine(s)
    print(json.dumps(eng.status(), indent=2))
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
    sp = sub.add_parser("import-janes")
    sp.add_argument("csv")
    _add_common(sp)

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
    elif args.cmd == "curate":
        cmd_curate(args, s)


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
