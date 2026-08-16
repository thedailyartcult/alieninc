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

If you need to republish longer excerpts or imagery from these sources, request
written permission and file it under `data/access/` before doing so.

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
