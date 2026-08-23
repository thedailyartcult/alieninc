# A-SAN Deep Scanner — Source Access & Licensing Policy

This is the compliance contract for the scanner. **Read before running.**

## 1. robots.txt and site terms are never bypassed

- The scanner enforces `robots.txt` via `urllib.robotparser` on every URL.
- A URL the site does not allow for our user-agent is **never fetched**.
- The `--no-robots` flag exists only as a hard stop: the engine refuses to run
  with it unless the site operator has **explicitly, in writing, whitelisted the
  scanner user-agent** (see §4). There is no silent bypass path in the code.

## 2. What "permission to use content" means

Creative Commons is a **content-licensing** scheme (what you may re-use in your
catalog), not a scraping permission. If the site operator granted CC rights for
our selected categories, keep the licence records (email/agreement) in
`data/access/` so every published entry can point at its reuse licence.

**Two separate things — do not confuse them:**
1. *May we fetch?* Answered by robots.txt + site ToS + operator whitelist.
2. *May we republish the data?* Answered by the content licence (e.g. CC BY).

### Fact-extraction-only sources (all-rights-reserved, no CC licence)

The following sources are © all-rights-reserved (no Creative Commons licence).
For these we use the **fact-extraction-with-attribution** pattern: only factual
data printed on the page (designation, dimensions, weights, ranges, country,
manufacturer) plus a short factual description is recorded, and every entry
carries the exact source URL. Wholesale prose reproduction is never done.

- **designation-systems.net** — © Andreas Parsch 2000-2026. See `/copyright.html`.
- **missilethreat.csis.org** — © Center for Strategic and International Studies.
  Each entry's description carries the verbatim "Cite this Page" citation string
  produced by CSIS for clean attribution.
- **modernfirearms.net** — © Maxim Popenker 1999-2026. Contact `admin@modernfirearms.net`.

### CC BY-SA source (freely republishable with attribution)

- **en.wikipedia.org** — Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0).
  Wikipedia content can be freely republished on the A-SAN website provided the
  source URL and licence are attributed. Every Wikipedia-sourced entry carries
  `SourceRef("Wikipedia (CC BY-SA 4.0)", <page_url>)` so the attribution chain
  is preserved in the catalog data. If you adapt or remix the content, the
  derivative must also be CC BY-SA 4.0 (ShareAlike).

If you need to republish longer excerpts or imagery from any all-rights-reserved
source, request written permission and file it under `data/access/` before doing
so.

## 3. Approved high-volume paths per source

| Source | Compliant path | Status |
|---|---|---|
| armyrecognition.com | Direct crawl of the **allowed** `/military-products/` tree (robots allows it; `?start=` pagination and admin paths are disallowed and skipped) | **Active** |
| patents.google.com | Direct fetch of patent pages (public, no key) | Active |
| worldwide.espacenet.com | **Official OPS API** (`ops.epo.org`) with free developer credentials; the web UI blocks autonomous fetches — the API is the sanctioned route | Requires OPS key/secret env vars |
| ppubs.uspto.gov | Official APIs (PatentsView / PEDS); the web app is browser-only | Manual / API pass |
| janes.com | **Paid licence** via research desk; CSV import (`import-janes`), never automated crawling | Licensed desk |
| militaryfactory.com | robots.txt imposes no crawl rules; scanner fetches with its UA. By-country list pages are also ingested from operator-supplied local HTML via `import-military` (site blocks some autonomous fetches, so local fallback is supported); detail pages are fetched live by the scanner to enrich specs. | Active |
| designation-systems.net | robots.txt allows `User-agent:*` for `/dusrm/` (detail pages) and `/usmilav/` (catalog index). No crawl-delay. Catalog enumeration via `/usmilav/missiles.html` (`table.designation-table`); detail pages `/dusrm/m-NN.html`. Wired in `parsers_designation.parse_designation`. | **Active** |
| missilethreat.csis.org | robots.txt allows `User-agent:*` (Disallow empty). **Crawl-delay: 10s** — enforced via `HttpFetcher.HOST_CRAWL_DELAY`. Catalog enumeration via `/missile/` dropdown (`select#item-select`); detail pages `/missile/<slug>/`. Wired in `parsers_missilethreat.parse_missilethreat`. | **Active** |
| modernfirearms.net | robots.txt allows `User-agent:*` for `/en/`. **Crawl-delay: 20s** — enforced via `HttpFetcher.HOST_CRAWL_DELAY`. Note: the bare category slugs (`/en/assault-rifles/`, `/en/handguns/`) 301→`/bez-rubriki/...`→404; use the long-slug URLs in `MODERNFIREARMS_SEED_URLS`. Detail pages `/en/<cat>/<country>-<cat>/<slug>/` are live. Wired in `parsers_modernfirearms.parse_modernfirearms`. | **Active** |
| milremrobotics.com | robots.txt allows `User-agent:*` (only AI bots — Amazonbot, Applebot-Extended, Bytespider — are disallowed). No crawl-delay for our UA. 6 UGV product pages (THeMIS family, HAVOC RCV, Vector RCV, MRCV, ARCOS, Type-X) with clean spec blocks. Wired in `parsers_milrem.parse_milrem`. | **Active** |
| man.fas.org | robots.txt: `User-agent:*` with `Disallow:` (empty — nothing disallowed). No crawl-delay. FAS Federation of American Scientists equipment reference at `/dod-101/sys/land/` (379 pages), `/ship/` (166), `/ac/equip/` (245). 501(c)(3) nonprofit — most license-permissive source. Two spec-table patterns (single-column + multi-variant). Wired in `parsers_fas.parse_fas`. | **Active** |
| en.wikipedia.org | robots.txt: `User-agent:*` allowed (the `/w/api.php` endpoint is the sanctioned high-volume route). No crawl-delay for polite fetchers. **Content licence: CC BY-SA 4.0** — this is the FIRST source whose content can be freely republished on the A-SAN website with attribution. Two page types: (1) "List of military electronics of the United States" (A–G + M–Z) with 1552 entries in wikitables (Designation/Purpose/Platform/Manufacturer); (2) individual EW system pages (AN/ALQ-99, AN/SLQ-32, Krasukha, etc.) with structured infobox spec tables. Wired in `parsers_wikipedia.parse_wikipedia_list` + `parse_wikipedia_infobox`. CLI: `python -m scan import-wikipedia`. | **Active** |
| war-sanctions.gur.gov.ua | robots.txt: `User-agent:*` `Allow:/` except `/office,/search,/api,/data,/subscription,/download-controller`. Cloudflare Content-Signals: `search=yes, ai-train=no, use=reference` — fact extraction with attribution is permitted; raw text must NOT be used for AI training/fine-tuning. Ukrainian government (GUR) portal run during an active war — fixed 3s/host delay via `HOST_CRAWL_DELAY`, far below any load concern. UAV catalog `/en/uav?page=N&per-page=12` → detail `/en/uav/<id>` ("Declared characteristics" spec blocks + related companies). Wired in `parsers_warsanctions.parse_warsanctions_uav`. CLI: `python -m scan discover-ua`. | **Active** |
| en.defence-ua.com | robots.txt: `User-agent:*` allowed except `/counter/,/search/,/pure/`, query strings (`/*?*`) and `*.php`. Detail URLs carry no query string — robots-clean. Discovery ONLY via the official monthly sitemaps (`defence-ua.com/sitemap/post-YYYY-MM.xml`) — never via `?page=N` listing pagination, which robots disallows. © Defence Express, all rights reserved — fact-extraction-with-attribution: spec tables + short description + exact source URL. Wired in `parsers_defenceua.parse_defenceua_article`. CLI: `python -m scan discover-ua --de-months 12`. | **Active** |

### Evaluated and rejected sources (2026-08 Ukraine-theater review)

- **militarnyi.com/en/** — Cloudflare hard block (403 challenge page even for
  browser-UA requests). Do not scrape; do not attempt WAF bypass.
- **usforces.army** — Unmanned Systems Forces recruiting/unit-profile site
  (robots fully open, but pages contain org history and vacancies, no equipment
  specifications). Not compatible with the equipment catalog data model; revisit
  only if a unit-order-of-battle module is ever scoped.
- **mod.gov.ua** — official MoD communications/news; low structured-spec density.
- **brave1.gov.ua** — robots all-allowed (`use=reference`), but the projects/
  product catalog is client-side rendered behind an internal JSON API. Revisit
  after an API discovery pass; 2,500 companies / 5,000+ products would be a
  major addition.
- **Warcrafted catalog (KI Insights / Tech Force in UA)** — subscriber PDF with
  verified manufacturer-provided specs; license it instead of scraping.

### Round-2 additions and rejections (2026-08-22)

| Source | Compliant path | Status |
|---|---|---|
| baykartech.com | robots: `User-agent:*` allows all except `/super/*`; EN sitemap `https://baykartech.com/en/sitemap.xml` lists `/en/uav/<slug>/` OEM product pages (TB2, TB3, Akinci, Kizilelma, K2, Mizrak, Kemankes…). Direct-manufacturer specs (Milrem pattern). Wired in `parsers_baykar.parse_baykar_product`. CLI: `discover-more`. | **Active** |
| army-guide.com | robots.txt EMPTY → allow-all (query-string listings OK). `/eng/products.php?pageNum=N` (~65 pages) → `/eng/productNNNN.html` detail pages with Designation/Manufacturer/Product-type metadata tables + Property/Value spec tables. Wired in `parsers_armyguide.parse_armyguide_product`. CLI: `discover-more`. | **Active** |
| www.globalsecurity.org | robots (2026-07-08): `User-agent:*` allowed except `/phpadsnew/`, webinator search; Content-Signals `search=yes, ai-input=no, ai-train=no, use=reference` — fact extraction permitted, NO AI training on its text; no Crawl-delay. Discovery BFS visits ONLY hub/index pages (`GS_HUB_PAGES` + index.html) and enqueues leaves unfetched — bounded politeness. Content pages: `<h2>` system name, prose specs. Wired in `parsers_globalsecurity.parse_globalsecurity`. CLI: `discover-more --gs-max-hubs N`. | **Active** |
| www.hisutton.com | robots absent (GitHub Pages) → allow-all. Flat article pages (`/<Article>.html`) on submarines/midget subs/SDVs/UUVs/surface craft. © H I Sutton — fact extraction with attribution. Wired in `parsers_hisutton.parse_hisutton_article`. CLI: `discover-more`. | **Active** |

Rejected in round 2:

- **navyrecognition.com** — 403 Forbidden on robots.txt itself (WAF-gated like
  militarnyi). Do not scrape.
- **military-today.com** — TCP connection refused; host unreachable/dead.
- **ukroboronprom.com.ua/en** — robots open, but the EN site is news +
  governance/compliance pages only; no product catalog post-rebrand to UOP.
- **sipri.org** — robots allow-all with Crawl-delay 10, but SIPRI is arms-transfer
  statistics (different data class from the equipment catalog) under CC BY-NC-ND;
  defer to a dedicated datasets module rather than shoehorning into entries.

### Round-3 additions and rejections (2026-08-23)

- **www.seaforces.org — ADDED.** robots: `User-Agent:* Disallow:` (empty =
  nothing disallowed); flat `sitemap.txt` enumerates every page (~2,800).
  Enqueued sections: `/wpnsys/` (naval weapon systems), `/usnships/`
  (US Navy classes + hulls), `/marint/<Country-Navy>/` (international navies).
  Deliberately skipped: `/usnair/`, `/usmcair/` (squadron/org pages, not
  equipment) and `/spcrep/`. Parser reads `<strong>Label:</strong>` spec
  blocks; designation from URL slug; country parsed from marint path.
  Wired in `parsers_seaforces.parse_seaforces`. CLI: `discover-seaforces`.
- **helis.com — REJECTED.** robots.txt itself returns 200, but all content
  paths serve a Cloudflare "Just a moment…" JS challenge to non-browser
  agents. Same class as militarnyi/navyrecognition: do not scrape, no WAF
  bypass.

## 4. Operator-whitelisted deep scan (rare, documented)

If a site operator gives us written permission to exceed robots.txt, the correct
procedure is:
1. Record the permission (grantor, date, scope, UA whitelist) in
   `data/access/permissions.json`.
2. Ask the operator to allow our UA in robots.txt **or** whitelist our egress IP.
3. Only then run with `--no-robots`, and **never** exceed the granted scope or
   reasonable rate limits (min 1s/host gap, single worker per host).

Absent step 1–2, `--no-robots` is a policy violation and must not be used.

## 5. Rate limits & politeness (defaults)

- Min `1.5 s` gap between requests to the same host; one in-flight request per host.
- Retries only on 429/5xx/network errors with exponential backoff; honours `Retry-After`.
- `Accept-Encoding: identity` (no compression tricks), clear user-agent:
  `ASAN-Scanner/1.0 (+A-SAN research catalog; ops@asan.local)`.

## 6. Data provenance rules

- Only data printed on the fetched page is stored. No inference, no completion.
- Every catalog entry keeps its exact source URL(s) and `fetched_at`.
- Raw HTML is cached locally so re-runs reuse it instead of re-hitting the site.
