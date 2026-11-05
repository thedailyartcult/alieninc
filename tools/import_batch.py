#!/usr/bin/env python3
"""Merge intake batches (labyu/_incoming/batch-*.json) into the sources of truth.

Each batch file: {"companies": [...], "founders": [...]} with the same schema
as companies.json / founders.json. Merge is idempotent: existing slugs are
skipped, so re-running is safe. Validates required fields + company_slug refs
(including refs resolved within the same batch).

Usage:
  python3 tools/import_batch.py            # merge all pending batch files
  python3 tools/import_batch.py --list      # show what would merge (dry run)

After merging: run tools/build-founders.py, then tools/generate-sitemap.py.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LABYU = ROOT / "labyu"
INC = LABYU / "_incoming"
FOUNDERS_JSON = LABYU / "founders.json"
COMPANIES_JSON = LABYU / "companies.json"

REQUIRED_F = ["slug", "name", "role", "company", "company_slug", "industry", "location"]
REQUIRED_C = ["slug", "name", "tagline", "status", "location"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check_company(c):
    for f in REQUIRED_C:
        if not str(c.get(f, "")).strip():
            raise ValueError(f"company missing required field {f}: {c.get('slug', '?')}")
    if not SLUG_RE.match(c["slug"]):
        raise ValueError(f"bad company slug: {c['slug']!r}")


def check_founder(r, known_companies):
    for f in REQUIRED_F:
        if not str(r.get(f, "")).strip():
            raise ValueError(f"founder missing required field {f}: {r.get('slug', '?')}")
    if not SLUG_RE.match(r["slug"]):
        raise ValueError(f"bad founder slug: {r['slug']!r}")
    if r["company_slug"] not in known_companies:
        raise ValueError(f"founder {r['slug']} references unknown company: {r['company_slug']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    founders = json.loads(FOUNDERS_JSON.read_text(encoding="utf-8"))
    companies = json.loads(COMPANIES_JSON.read_text(encoding="utf-8"))
    fslugs = {r["slug"] for r in founders}
    cslugs = {c["slug"] for c in companies}
    batches = sorted(INC.glob("batch-*.json")) if INC.exists() else []
    if not batches:
        print("No intake batches found in labyu/_incoming/")
        return 0
    new_c, new_f, skipped = [], [], []
    for path in batches:
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data.get("companies", []):
            check_company(c)
            if c["slug"] in cslugs:
                skipped.append(f"{path.name}:company:{c['slug']}")
            else:
                new_c.append(c)
                cslugs.add(c["slug"])
        for r in data.get("founders", []):
            check_founder(r, cslugs)
            if r["slug"] in fslugs:
                skipped.append(f"{path.name}:founder:{r['slug']}")
            else:
                new_f.append(r)
                fslugs.add(r["slug"])
    print(f"Batches: {len(batches)} | new companies: {len(new_c)} | "
          f"new founders: {len(new_f)} | skipped (dup): {len(skipped)}")
    for s in skipped:
        print(f"  skip {s}")
    if args.list:
        return 0
    if new_c:
        companies.extend(new_c)
        COMPANIES_JSON.write_text(json.dumps(companies, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    if new_f:
        founders.extend(new_f)
        FOUNDERS_JSON.write_text(json.dumps(founders, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(f"Merged. Totals: {len(companies)} companies, {len(founders)} founders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
