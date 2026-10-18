# Technical SEO Findings — alieninc.tech

Crawl scope: 357 sitemap URLs (8 subdomains + thedailyartcult.lol).
Crawler: requests + BeautifulSoup, concurrency 8, 20s timeout.

## What works

- `sitemap.xml` reachable, urlset format, 357 URLs.
- `robots.txt` reachable, well-commented, blocks `/data/`, `/api/`, `/engine/`, `/internal/`, `/admin/`, `/vault/`, `/moderation/`.
- 356/357 URLs return HTTP 200.
- Unknown URLs return a real 404 page with `noindex` (good — not a soft 404).
- HTTPS + HSTS preload, CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, strict Referrer-Policy.
- Served behind Cloudflare + Fastly, gzip, edge cache in MNL.

## Findings

### High — 120 pages missing canonical
Crawl found 120/357 sitemap URLs without `<link rel="canonical">`. Duplicate-content
risk across the subdomain set (panteon vs secure.alieninc.tech both title "Panteon —
Secure Portal").

**Fix:** self-referencing canonical on every page. `tools/inject-seo.py` already does
this for 8 subdomain roots; extend it to all subpages, or emit canonicals at build time.

### Medium — sitemap lists a 404
`https://alieninc.tech/trust/index.html` returns 404 but is in `sitemap.xml`.
Google treats this as a crawl-budget / quality signal.

**Fix:** remove from the sitemap, or restore the page (the `/trust/` path is
referenced in the homepage meta `compliance` tag as `report=/trust/`).

### Low — duplicate titles
- `articles/2026/09/24/The-Alien-Minds-We-Built.html` and
  `articles/2026/09/24/index.html` share title + description.
- `panteon.alieninc.tech/login.html` and `secure.alieninc.tech/` share
  `Panteon — Secure Portal`.

**Fix:** canonicalize one variant per pair; prefer the pretty URL.
