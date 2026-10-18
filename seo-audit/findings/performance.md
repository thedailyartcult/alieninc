# Performance / CWV Findings — alieninc.tech

Status: **lab and field data not collected.**

## Why

`pagespeed_check.py` (PageSpeed Insights v5 + CrUX combined) requires a Google
API key:

```
Error: CrUX API requires an API key. Use --api-key or configure GOOGLE_API_KEY.
```

No `GOOGLE_API_KEY` is configured on this machine, so Lighthouse lab metrics
(LCP, INP, CLS, TBT) and CrUX field data (real-user p75) were **not** measured.
This is an honest gap, not a pass.

**To close it:** obtain a Google API key with PageSpeed Insights enabled, then:

```bash
export GOOGLE_API_KEY=...
python3 scripts/runtime.py run pagespeed_check.py https://alieninc.tech --strategy both --json
```

## What we can infer from headers (no key needed)

| Signal | Observation | Implication |
|---|---|---|
| Edge | Cloudflare + Fastly, `X-Cache: MISS`, `X-Served-By: cache-mnl2150026-MNL` | Double CDN; origin is GitHub Pages (`X-GitHub-Request-Id`) |
| Compression | `Content-Encoding: gzip` | Brotli would be better for text HTML |
| Caching | `Cache-Control: max-age=600`, `cf-cache-status: DYNAMIC` | 600s TTL but Cloudflare is **not** caching the HTML (`DYNAMIC`) — every request hits origin |
| HTML size | 242,846 chars raw on homepage | Large static HTML; gzip helps but this is heavy for LCP |
| JS render | `is_spa: null`, no render required | **Good** — no SPA hydration delay on primary content |

### Medium — homepage HTML is not edge-cached
`cf-cache-status: DYNAMIC` means Cloudflare is bypassing cache for HTML. With
`Cache-Control: max-age=600` set, the origin (GitHub Pages via Fastly) serves
every request. For a mostly-static corporate site this is free performance
left on the table.

**Fix:** set a Cloudflare Cache Rule / Page Rule to cache HTML for
`alieninc.tech/*` with a longer TTL, and `Bypass Cache on Cookie` if any
auth'd routes exist. Verify `trust/`, `dashboard.html`, and any cookie-gated
paths stay uncached.

### Low — Google Fonts loaded render-blocking from origin
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Ultra&family=Alfa+Slab+One&family=Instrument+Sans...">
```
Three families (Ultra, Alfa Slab One, Instrument Sans). `preconnect` helps,
but the CSS is still render-blocking and the fonts are third-party.

**Fix:** self-host the woff2 subsets (they're already used as brand fonts) or
at minimum add `font-display: swap`. Self-hosting also removes a third-party
request, which is consistent with the site's strict CSP posture.

## Bottom line
Technical foundation is solid (static HTML, no SPA, double CDN). The two
actionable wins without any API key: **enable HTML edge caching**, and
**self-host fonts**. Get a PSI key to turn this from inference into measured
p75 LCP/INP/CLS.
