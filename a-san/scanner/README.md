# A-SAN Deep Scanner

Robots-compliant, resumable, category-aware crawler that deep-scans the approved
public sources and merges results into the A-SAN catalog schema
(`catalog-data.json`). Built to run **again and again** until the selected
categories are exhausted — designed for thousands of entries.

**Policy first:** read `POLICY.md`. robots.txt is always honoured; espacenet and
janes are accessed via their official/licensed paths, never bypassed.

## Install

Python 3.10+ — **stdlib only, no pip install needed.**

```
cd scanner
python -m scan run --categories aircraft,uavs --limit 10   # smoke test
```

## Pipeline

```
seed      load existing catalog + seeds/categories.json into the queue (dedupe-aware)
discover  sitemap enumeration: /military-products product URLs + news article URLs,
          classified into the 11 categories, enqueued (product + article + patent kinds)
crawl     fetch (robots-gated, cached, polite) -> host-dispatched parser -> upsert+dedupe
export    write catalog-data.json (schema v1.0, grouped by category)
curate    RAW POOL -> filters -> scoring -> ranked PICKLIST (+ audit)
build-web write static site (category.html + data/) to the site root, design-faithful to index.html
patent-feed enqueue patent pub-numbers (USPTO ODP / Espacenet OPS / --patents-file)
import-military ingest operator-scraped militaryfactory.com "Aircraft by Country"
              pages (scanner/data/military/*.html) — merged by stable aircraft_id,
              civilian-only types dropped, operators accumulated
```

The engine dispatches each host to a source-specific parser:
`armyrecognition.com` → `parse_armyrecognition`; `patents.google.com` →
`parse_patent`; `weaponsystems.net` → `parse_weaponsystem`. To add a site, add a
parser + a host branch in `engine._process` (see PLAN.md §1 "Adding a source").

Every run is **resumable**: the queue lives in `data/scan.db` (SQLite WAL). A
killed run restarts where it left off. Raw HTML is cached so `--refresh` is the
only thing that re-fetches.

## The picklist mission

A-SAN generates a **picklist from a raw pool** — that is the user-facing product.

- **Raw pool** = every candidate the scanner acquired that passed *base
  admission*: approved source, robots-allowed, fetched & parsed into the schema,
  deduped. Nothing else enters.
- **Picklist** = the curated, scored, ranked, bounded subset of the raw pool
  that the user is shown for decision-making. The user only ever sees the
  picklist.

`python -m scan curate` runs the full curation pipeline:

```
raw pool ──► hard filters ──► weighted scoring ──► per-category top-N ──► picklist
```

**Hard filters (exclusion):** no source URL, empty content (no specs *and* no
description), designation shorter than 3 chars.

**Scoring (0–100, weighted, deterministic):**

| Dimension | Weight | Measures |
|---|---|---|
| completeness | 0.35 | description length, # specs, country, manufacturer, alt names |
| source_quality | 0.25 | product page > patent > news; spec table present |
| category_confidence | 0.15 | classifier rule specificity (rule 0 = most specific) |
| recency | 0.10 | days since fetch |
| coverage | 0.15 | rarity bonus so sparse categories aren't drowned out |

Ranking is score desc (tie-break: designation alpha). `--min-score` (default 40)
excludes low-quality candidates; `--max-per-category` (default 15) bounds each
category; `--max-total` (default 100) caps the whole picklist.

Every run is **fully automated, deterministic and audited**: weights are
versioned, each entry carries `_score` + `_score_breakdown`, and the exclusion
counts per rule are written to `data/picklist.json` alongside the ranked entries.

**Picklist entry anatomy** (what the user sees in `picklist.csv` / the future UI):
`rank, category, score, designation, alt_names, country, manufacturer,
description, key_specs, source_urls`.

## Commands

| Command | Purpose |
|---|---|
| `python -m scan run` | Full cycle for all 11 categories |
| `python -m scan run --categories uavs,small-arms --limit 100` | Scoped run |
| `python -m scan discover` | Enqueue sitemap product URLs only (10 sources now) |
| `python -m scan crawl` | Continue a partial run |
| `python -m scan status` | Queue + entry counts |
| `python -m scan export` | Rebuild catalog-data.json from the store |
| `python -m scan curate` | Raw pool → picklist (`data/picklist.json` + `.csv`) |
| `python -m scan build-web` | Static site — `category.html` + `data/` at the site root (11 categories) |
| `python -m scan import-janes desk.csv` | Ingest licensed research-desk CSV |
| `python -m scan patent-feed --query "guided missile defense" --category "Rocket and missile weapons" --limit 500` | Enqueue 500 patent URLs (USPTO ODP / Espacenet OPS; or `--patents-file list.txt`) → then `crawl` |

## Flags

```
--categories uavs,ew-assets   comma-separated (keys or display names)
--limit 500                   cap product pages this run
--delay 1.5                   min seconds between requests per host
--workers 1                   parallel hosts (per-host politeness always kept)
--refresh                     ignore the raw-HTML cache and re-fetch
--catalog PATH                output catalog path (default ../catalog-data.json)
--db PATH                     scan store path (default data/scan.db)
```

## Scaling for the high-end server

- Keep `--workers` modest (2–6); per-host throttling is the real limit.
- Run category-scoped batches so a failure only affects one category:
  `python -m scan run --categories naval-vessels --limit 500`
- Schedule repeated runs (cron / systemd timer) — the store is idempotent and
  merges, never duplicates.
- To reach **thousands/hundreds of thousands** of entries: the high-volume lever
  is a feed of publication numbers — e.g. the new **USPTO Open Data Portal** API
  (requires USPTO.gov account + key + MFA; the legacy `ppubs.uspto.gov` API
  migrated in Aug 2026). Each publication number becomes a
  `patents.google.com/patent/<pub>/en` URL → `scan seed` a list → `crawl` (the
  `patents.google.com` parser is already wired). See `PLAN.md §5`.
- `python -m scan build-web` is **not automatic** — re-run it after a crawl to
  refresh `web/data/*.json`; serve with `python3 -m http.server 8000 --directory web`.

## Espacenet / Janes / USPTO

- **Espacenet**: set `ESPACENET_OPS_KEY` / `ESPACENET_OPS_SECRET` (free EPO OPS
  developer account) — the official API client is wired in `parsers.EspacenetOPS`.
- **Janes**: licensed research desk exports a CSV; `import-janes` ingests it.
- **USPTO**: use the official PatentsView/PEDS APIs (see `parsers.uspto_help`).

## Output

`../catalog-data.json` — same schema as v1.0 (`designation`, `alt_names`,
`country`, `manufacturer`, `category`, `description`, `specs[]`,
`sources[{label,url}]`), grouped by the 10 canonical categories with counts.

`data/picklist.json` + `data/picklist.csv` — the curated, ranked picklist for
user decision-making (see "The picklist mission" above).

`web/` — static browser site: `web/index.html` links to `web/category.html`,
which reads the per-category JSON in `web/data/` (template lives at
`web/templates/category.html`). Serve with `python3 -m http.server 8000
--directory web`.
