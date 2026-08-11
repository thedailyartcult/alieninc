# A-SAN — Defense & Aerospace Catalog: Operations Plan

**Operation:** Stand up the A-SAN technical catalog from public sources only.
**Primary workspace:** `/home/alieninc/a-san/`
**Status:** v1 data acquisition complete (2026-08-11); automated deep scanner live —
crawled the full `armyrecognition.com` sitemap (1,437 product URLs) + seeded entries,
yielding 1,473 parsed catalog entries (up from the original 44) across 11 categories.
A second source (`patents.google.com`) is wired into the engine and produces entries;
USPTO PEDS has migrated to a gated API (see §2 / Phase 5).

---

## 1. Mission

Build the A-SAN catalog following the existing design language in `index.html`
(Lato typography, brand red `#ea4335`, 1200px layout, 3/4-column card grid,
teaser + locked-overlay access pattern). Every catalog entry must be populated
exclusively with **publicly documented data** drawn from the approved source set,
with clean, clickable source links on every entry. **Nothing invented, nothing
inferred.**

## 2. Approved source set (access matrix, tested 2026-08-11)

| Source | Reachable from this server | Role |
|---|---|---|
| `armyrecognition.com` | Yes — full product pages via fetch; sitemap enumerated | **Primary**: 1,473 entries across 10 product categories |
| `patents.google.com` | Yes — full patent records via fetch | **Secondary (live)**: patent records, wired into the engine |
| `ppubs.uspto.gov/pubwebapp` | 404 — **migrated**. New USPTO Open Data Portal now requires a USPTO.gov account + API key + MFA (Aug 2026). | Secondary: USPTO records (now gated) |
| `worldwide.espacenet.com` | **No** — robots.txt + 403 (use official OPS API w/ credentials) | Research-desk or licensed pass |
| `janes.com` | **No** — robots.txt | Licensed research-desk pass |

**Doctrine:** a system is only included if at least one approved page was actually
fetched and its data read. Unreachable sources are never cited from memory.

**Scale lever:** the catalog is fed by an idempotent, resumable queue
(`python -m scan discover` pulls the sitemap; `python -m scan crawl` drains it,
per-host polite, robots-gated). To reach thousands of entries, add a high-volume
feed (e.g. USPTO patent publication numbers → `patents.google.com/patent/…` URLs
→ `enqueue`), then `crawl`. The engine dispatches each host to its parser
(`armyrecognition` → `parse_armyrecognition`; `patents.google.com` →
`parse_patent`). Adding a source = new parser + a host branch in
`engine._process` (see `scan/scan/engine.py`).

## 3. Phase 0 — Design baseline (complete)

Design tokens locked from `index.html` (see `index.html:13-532`):

- Font `Lato` 300/400/700; brand red `#ea4335`, link `#d93025`, hover `#b31412`
- Text `#202124`, muted `#5f6368`, border `#dadce0`, bg-light `#f8f9fa`
- Sticky 72px header + dropdown nav; `cards-grid` (4col → 2col → 1col),
  `cards-grid-3`; `.item-card`/`.category-card` (white, 1px border, 8px radius,
  24px padding, min-height 200px); `.ir-link` red links; `.teaser-box` /
  `.locked-overlay` restricted-access pattern; `.spec-table` (th 40%).
- Brand voice: "ASEAN Superiority Aerospace Navigator"; restrained, factual.

## 4. Phase 1 — Data acquisition (done: automated deep crawl, 1,552 entries)

The scanner (`scanner/`) automates the full pipeline: `seed` (existing catalog +
`seeds/categories.json`) → `discover` (sitemap enumeration of all 1,733
`/military-products/` product URLs, classified into the 11 categories) → `crawl`
(robots-gated, polite, cached, resumable fetch + parse + dedupe) → `export` /
`build-web`. One run drained all 1,437 sitemap URLs and produced 1,552 live entries.

### Category coverage — current

| # | Key | Category | Entries |
|---|---|---|---|
| 1 | aircraft | Aircraft | 156 |
| 2 | uavs | UAVs | 29 |
| 3 | air-launched-munitions | Air-launched munitions | 19 |
| 4 | rocket-and-missile-weapons | Rocket and missile weapons | 442 |
| 5 | sea-launched-cruise-missiles | Sea-launched cruise missiles | 28 |
| 6 | ew-assets | EW assets | 19 |
| 7 | ugvs | UGVs | 19 |
| 8 | armored-vehicles-and-equipment | Armored vehicles and equipment | 624 |
| 9 | automotive-vehicles | Automotive vehicles | 58 |
| 10 | small-arms | Small arms | 80 |
| 11 | naval-vessels | Naval vessels | 78 |

**Total ≈ 1,552 entries** (live count in `scan.db` / `web/data/categories.json`).
`Rocket and missile weapons` and `Armored vehicles` dominate because Army
Recognition has deep coverage there; `UAVs` / `UAVs-small` are thin.

**Patent pass (live):** `patents.google.com` is wired into `engine._process` →
`parse_patent`. Patent pages are fetched, the title/abstract/publication are
captured, and records enter the catalog under their assigned category. This is
the secondary scale lever (to reach thousands/hundreds-of-thousands, feed USPTO
publication numbers as Google-Patents URLs into the queue and re-`crawl`).

### Adding a category (procedure)

1. `scan/config.py`: add display name to `CANONICAL_CATEGORIES` (ordered list),
   `"key": "Display name"` to `CATEGORY_KEYS`, and a `(key, [path-keywords])` rule
   to `CATEGORY_RULES` — **before** the broad `aircraft` (`"air/"`) / generics
   so specific paths win (rule order is decisive).
2. `seeds/categories.json`: add `"key": [verified_product_urls]`.
3. `python -m scan seed` → `python -m scan discover` → `python -m scan crawl --limit N`
   → `python -m scan build-web` (or `python -m scan export` for `catalog-data.json`).

### Adding a source (procedure)

1. `POLICY.md` / `PLAN.md §2`: add the host to the approved matrix with its
   compliant path and status.
2. `scan/parsers.py`: write `parse_<host>(url, html, category, …)` returning a
   `CatalogEntry` using only fields printed on the page.
3. `scan/config.py`: add the host to `Settings.domains`.
4. `scan/engine.py`: add an `elif host == "…":` branch in `_process` calling the
   new parser (see the `patents.google.com` branch as a template).
5. Re-run `discover`/`crawl`/`build-web`.

## 5. Phase 2 — Data structuring & QA (complete)

- Single canonical schema per entry (see `catalog-data.json`):
  `designation`, `alt_names`, `country`, `manufacturer`, `category`,
  `description`, `specs[]`, `sources[{label,url}]`.
- Category field normalized to the 10 canonical categories; vehicle subtype
  (MBT / IFV / cargo truck…) preserved as the first `Type:` spec line.
- QA rules enforced: no field that did not appear on a fetched page; source
  conflicts on the same page kept verbatim and flagged in the description
  (e.g. Switchblade range, Wing Loong endurance) rather than "fixed".
- Source policy is embedded in the JSON (`source_policy`) so downstream pages
  cannot silently mix in unverified data.

## 6. Phase 2.5 — The picklist mission (curation model, decided 2026-08-11)

A-SAN's core product is **a picklist generated from a raw pool**. The user sees
only the picklist; it is the decision-making artifact. This model is baked into
the scanner (`python -m scan curate`) and every future dataset must define its
own raw pool → picklist → selection logic.

**Raw pool** — every candidate the scanner acquired that passed base admission:
approved source, robots-allowed, fetched & parsed into the schema, deduped.
Nothing else. For armyrecognition.com this is the ~1,693 sitemap product URLs in
the `/military-products/` tree (all robots-allowed) + seeded catalog entries.

**Picklist** — the curated, scored, ranked, bounded subset of the raw pool.
Fully automated, deterministic, audited. Same input → same output.

**Selection logic** (all data, versioned in the audit file):
1. *Hard filters*: no source URL / empty content / weak designation → exclude.
2. *Weighted scoring* (0–100): completeness 0.35 · source quality 0.25 ·
   category confidence 0.15 · recency 0.10 · coverage/rarity 0.15.
3. *Ranking*: score desc, designation-alpha tie-break.
4. *Bounds*: `--min-score` 40, `--max-per-category` 15, `--max-total` 100.

**Picklist entry anatomy** (exactly what the user sees): `rank, category, score,
designation, alt_names, country, manufacturer, description, key_specs,
source_urls` — with per-entry `_score_breakdown` so the user can see *why*.

**Constraints enforced per dataset**: approved sources only, public data only,
no fabrication, no humans in the loop, no commercial/proprietary/classified, no
paywalled content, rules-driven, automated audit. Every curate run writes
`data/picklist.json` (with exclusion counts per rule + weights version) +
`data/picklist.csv`.

**UX**: the picklist is a new experience for the user — no incumbency. It will
render as decision cards (rank badge, designation, category, country, 1–2 line
description, top key specs, clickable approved source links, score + "why"
breakdown, and the user's decision). Design tokens from `index.html`.

## 7. Phase 3 — Catalog implementation (next)

Build `catalog.html` (or fold into `index.html`) using only the existing design
system:

1. **Category landing** — reuse the 10 `.category-card` tiles already in
   `index.html`; wire every "View category" link to its section.
2. **Category sections** — `.cards-grid-3` of `.item-card` per category, each
   card showing `detail-meta` (category · country · manufacturer), `card-heading`
   (designation), `card-description` (public summary), and a red "View profile"
   link.
3. **Item detail pages** — `.detail-header` (meta + title + subtitle), `.spec-table`
   of key public specs, then the existing `.locked-overlay` teaser for any
   full-profile content that requires verified access. Public spec table is the
   only content shown to unauthenticated visitors.
4. **Source links** — every profile renders its `sources[]` as `.ir-link` red
   links to the Army Recognition page (and later patent records).
5. **Responsive + mobile nav** — inherit unchanged from `index.html` (`<768px`
   hamburger menu, stacked cards, footer).

No new design tokens. If a token is missing, it is a bug, not a reason to invent.

## 8. Phase 4 — Access control (design-aligned)

Mirror the existing teaser/locked language exactly:

- Public: category cards + summary + public spec table + source links.
- Verified: full technical profiles, component analysis, drawings, research
  notes — behind the existing `.locked-overlay` + `Request Access` CTA.

## 9. Phase 5 — Research-desk expansion roadmap

1. **Patent pass (live)** — `patents.google.com` records are ingested via the
   wired engine pass. For high volume: pull USPTO publication numbers from the
   **new USPTO Open Data Portal** (requires USPTO.gov account + API key + MFA,
   Aug 2026 migration — the legacy `ppubs.uspto.gov/pubwebapp` API is gone), turn
   each into a `patents.google.com/patent/<pub>/en` URL, `enqueue`, and `crawl`.
2. **Espacenet pass** — Espacenet web UI blocks autonomous fetches; use the
   official **OPS API** (`ops.epo.org`, free EPO developer account) which the
   engine already has a client stub for (`parsers.EspacenetOPS`, wired to
   `ESPACENET_OPS_KEY`/`ESPACENET_OPS_SECRET` env vars).
3. **Janes pass** — licensed research-desk CSV; `import-janes` (read-only ingest,
   never crawled).
4. **Category deepening** — add systems until each category holds ≥6 entries;
   prioritise Automotive (HEMTT variants, JLTV variants), Small arms (M16, FAL,
   G36, P90) and EW (more Krasukha variants, NGJ-Low).
5. **Monthly refresh** — re-fetch changed pages, supersede stale entries, archive
   removed systems; record each cycle in CMB.

## 10. Deliverables

| Item | Path | Status |
|---|---|---|
| Design baseline (from `index.html`) | in this plan | Done |
| Structured catalog data (44 entries) | `catalog-data.json` | Done |
| Deep scanner (raw pool engine) | `scanner/` | Done |
| Picklist generator (curation model) | `scanner/scan/picklist.py` | Done |
| Category coverage (11 categories) | `scan/config.py` + `web/data/categories.json` | Done |
| Second source wired (patents.google.com) | `scan/engine.py` `parse_patent` | Done |
| Static web export (design-aligned) | `scanner/web/` (`build-web`) | Done |
| Operations plan | `PLAN.md` | Done |
| Catalog pages (v1) | `catalog.html` (proposed) | Next |
| Picklist UI (decision cards) | — | Next |

## 11. Verification & hygiene

- Validate `catalog-data.json` after every edit (`json.load` + category/count
  assertions).
- Every added entry must carry ≥1 actually-fetched source URL — enforced during
  the build phase, not after.
- Store durable decisions in CMB (`alieninc` / `a-san`) as they happen; never
  store raw page dumps.
