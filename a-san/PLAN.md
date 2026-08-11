# A-SAN — Defense & Aerospace Catalog: Operations Plan

**Operation:** Stand up the A-SAN technical catalog from public sources only.
**Primary workspace:** `/home/alieninc/a-san/`
**Status:** Plan + first data acquisition complete (2026-08-11)

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
| `armyrecognition.com` | Yes — full product pages via fetch | **Primary**: detailed product spec pages |
| `patents.google.com` | Yes — full patent records via fetch | Secondary: patent/technical records |
| `ppubs.uspto.gov/pubwebapp` | Partial — JavaScript app | Secondary: USPTO records (manual/browser pass) |
| `worldwide.espacenet.com` | **No** — robots.txt + 403 | Manual research-desk or licensed pass |
| `janes.com` | **No** — robots.txt | Manual research-desk or licensed pass |

**Doctrine:** a system is only included if at least one approved page was
actually fetched and its data read. Unreachable sources are never cited from
memory.

## 3. Phase 0 — Design baseline (complete)

Design tokens locked from `index.html` (see `index.html:13-532`):

- Font `Lato` 300/400/700; brand red `#ea4335`, link `#d93025`, hover `#b31412`
- Text `#202124`, muted `#5f6368`, border `#dadce0`, bg-light `#f8f9fa`
- Sticky 72px header + dropdown nav; `cards-grid` (4col → 2col → 1col),
  `cards-grid-3`; `.item-card`/`.category-card` (white, 1px border, 8px radius,
  24px padding, min-height 200px); `.ir-link` red links; `.teaser-box` /
  `.locked-overlay` restricted-access pattern; `.spec-table` (th 40%).
- Brand voice: "ASEAN Superiority Aerospace Navigator"; restrained, factual.

## 4. Phase 1 — Data acquisition (complete for v1, 44 entries)

Workflow per system: websearch for the Army Recognition product page → fetch the
full page (page-through on truncation) → extract only data printed on the page →
record the exact source URL. Patent records (Google Patents) reserved for the
follow-up pass.

### Category coverage — v1

| # | Category | Entries | Verified systems |
|---|---|---|---|
| 1 | Aircraft | 5 | F-35A, F-16A/B, Su-57, Chengdu J-20, Dassault Rafale |
| 2 | UAVs | 5 | MQ-9 Reaper, Bayraktar TB2, Shahed-136, Wing Loong II, Switchblade 300 |
| 3 | Air-launched munitions | 4 | AIM-120 AMRAAM, JDAM (GBU-31), Storm Shadow/SCALP-EG, AGM-158 JASSM |
| 4 | Rocket and missile weapons | 5 | M142 HIMARS, MIM-104 Patriot, S-400, Iskander-M, MGM-140 ATACMS |
| 5 | Sea-launched cruise missiles | 5 | BGM-109 Tomahawk, 3M-54 Kalibr, NSM, P-800 Oniks, Exocet MM40 B3C |
| 6 | EW assets | 4 | Krasukha-4 (1RL257), AN/SLQ-32, Pole-21, AN/ALQ-249 NGJ-MB |
| 7 | UGVs | 4 | Uran-9, Milrem THeMIS, Mission Master SP, MUTT |
| 8 | Armored vehicles and equipment | 5 | M1 Abrams, Leopard 2A8, T-90M, Challenger 2, BMP-3 |
| 9 | Automotive vehicles | 3 | HEMTT M977 A2, JLTV L-ATV, IVECO LMV |
| 10 | Small arms | 4 | AK-12, FN SCAR L MK2, FAMAS, M16A2 |

**Total: 44 entries.** Data lives in `catalog-data.json` (schema v1.0).

### Known gaps (open threads)

- **Automotive / Small arms** are the thinnest categories — Army Recognition
  product coverage is sparser there. MAN HX2, Ural-4320, Tatra T810, Steyr AUG,
  HK MP5, FN P90, M4/HK416/M249 were attempted and have no verifiable Army
  Recognition product page.
- **EW assets** have few dedicated product pages; several entries are sourced
  from fetched Army Recognition news/focus articles instead.
- **espacenet / janes / USPTO** entries: zero so far (blocked from server).
  Requires the research-desk pass (Phase 5).

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

1. **Patent pass** — for each system, attach one Google Patents record
   (`patents.google.com/patent/…`) verified by fetch; build a lookup table of
   representative patents (e.g. Kalibr/3M-54, Iskander 9M723, JASSM, Exocet).
2. **USPTO pass** — `ppubs.uspto.gov` records via browser/research desk.
3. **Espacenet pass** — licensed/manual; add publication numbers + URLs.
4. **Janes pass** — licensed/manual; use for cross-check and gap filling.
5. **Category deepening** — add systems until each category holds ≥6 entries;
   prioritise Automotive (HEMTT variants, JLTV variants), Small arms (M16,
   FAL, G36, P90) and EW (more Krasukha variants, NGJ-Low).
6. **Monthly refresh** — re-fetch changed pages, supersede stale entries,
   archive removed systems; record each cycle in CMB.

## 10. Deliverables

| Item | Path | Status |
|---|---|---|
| Design baseline (from `index.html`) | in this plan | Done |
| Structured catalog data (44 entries) | `catalog-data.json` | Done |
| Deep scanner (raw pool engine) | `scanner/` | Done |
| Picklist generator (curation model) | `scanner/scan/picklist.py` | Done |
| Operations plan | `PLAN.md` | Done |
| Catalog pages (v1) | `catalog.html` (proposed) | Next |
| Picklist UI (decision cards) | — | Next |
| Patent/Espacenet/Janes additions | — | Roadmap |

## 11. Verification & hygiene

- Validate `catalog-data.json` after every edit (`json.load` + category/count
  assertions).
- Every added entry must carry ≥1 actually-fetched source URL — enforced during
  the build phase, not after.
- Store durable decisions in CMB (`alieninc` / `a-san`) as they happen; never
  store raw page dumps.
