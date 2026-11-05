# Full SEO Audit — alieninc.tech

**Audited:** 2026-10-18
**Method:** claude-seo v2.4.0 (AgriciDaniel/claude-seo), run standalone via
`scripts/runtime.py` on the bundled Python 3.13 + Playwright runtime. Sitemap
crawl: 357 URLs, concurrency 8, requests + BeautifulSoup. Tools used:
`fetch_page.py`, `parse_html.py`, `content_quality.py`, `agentic_check.py`,
`sitemap_discovery.py`, `pagespeed_check.py`, `seo_updates.py`, `google_report.py`.

---

## Executive summary

| | |
|---|---|
| **Overall SEO Health Score** | **74 / 100** |
| Business type | Multi-company operating group / AI infrastructure (corporate umbrella) |
| Pages crawled | 357 (200: 356, 404: 1) |
| Homepage content quality | 96/100 |

**The one-line read:** Alien Inc's *homepage is excellent* — 96/100 content
quality, a valid Organization + Person JSON-LD graph, strong E-E-A-T, and a
clean static-HTML architecture that AI crawlers can read without JavaScript.
The *long tail is neglected*: roughly a third of the site is missing canonicals,
meta descriptions, Open Graph tags, and structured data. And the site
simultaneously advertises AI readiness (`Content-Signal`, WebMCP annotations)
while `robots.txt` blocks ten AI crawlers — the single biggest strategic
contradiction in the audit.

---

## Score by category

| Category | Weight | Score | Weighted |
|---|---|---|---|
| Technical SEO | 22% | 78 | 17.2 |
| Content Quality | 23% | 92 | 21.2 |
| On-Page SEO | 20% | 70 | 14.0 |
| Schema / Structured Data | 10% | 85 | 8.5 |
| Performance (CWV) | 10% | 70 | 7.0 |
| AI Search Readiness | 10% | 55 | 5.5 |
| Images | 5% | 60 | 3.0 |
| **Total** | **100%** | | **76.4 → rounded 74** |

*(Rounded down to 74 to account for the unmeasured CWV category — Performance
is scored on header inference, not measured LCP/INP/CLS, so the 70 is an
estimate, not a measurement.)*

---

## Top findings

1. **Homepage + article index are well-structured** — valid Organization schema,
   868 words, 96/100 content quality, solid security headers, no SPA render
   dependency. This is a genuine strength and should not be rewritten.
2. **120 of 357 sitemap URLs lack a canonical tag**; 115 lack Open Graph and
   Twitter Card meta. Roughly one third of the site has no social-preview or
   duplicate-content control.
3. **112 pages have no meta description** (31% of indexed URLs); **46 pages have
   no H1**, concentrated on `panteon.alieninc.tech` subpages.
4. **`llms.txt` returns 404.** Lighthouse drops the agentic-readiness audit from
   its fraction; publishing a valid one adds a counted pass. Cheap, high-signal.
5. **`robots.txt` blocks 10+ AI crawlers** (GPTBot, CCBot, Google-Extended,
   PerplexityBot, Claude-Web, Bytespider, Diffbot…), contradicting the site's
   own AI-readiness posture. This is a *policy decision*, not a bug — but if
   GEO/AI Overviews visibility is a goal, `Google-Extended` and `PerplexityBot`
   should be reconsidered.
6. **One sitemap URL 404s:** `https://alieninc.tech/trust/index.html`.
7. **`logo.png` uses `alt="•"` on every page** — a bullet is not a valid alt
   value; correct fix is `alt=""` (the brand link already has `aria-label`).
8. **Duplicate titles:** the `/articles/2026/09/24/` article and its
   `index.html` variant share title + description; `panteon login.html` and
   `secure.alieninc.tech` share "Panteon — Secure Portal".
9. **CWV not measured** — `pagespeed_check.py` needs a `GOOGLE_API_KEY`. What
   we *can* see: Cloudflare reports `cf-cache-status: DYNAMIC`, so the homepage
   HTML is **not edge-cached** despite a 600s TTL — free performance left on
   the table.

---

## Quick wins (do these first)

| # | Action | Effort | Impact |
|---|---|---|---|
| 1 | Publish `/llms.txt` (H1 + `>` summary + markdown links to the 7 portals) | 30 min | High — counted Lighthouse pass + AI-answer surface |
| 2 | Decide the AI-crawler policy; unblock `Google-Extended` + `PerplexityBot` if GEO matters | 5 min | High — directly gates AI Overview visibility |
| 3 | Remove `/trust/index.html` from `sitemap.xml` (or restore the page) | 5 min | Medium — crawl hygiene |
| 4 | Fix `logo.png` → `alt=""`, add `width`/`height` | 10 min | Low-Med — a11y + CLS |
| 5 | Enable Cloudflare HTML cache rule for `alieninc.tech/*` | 30 min | Medium — free TTFB/LCP win |
| 6 | Canonicalize the duplicate title pairs | 15 min | Low |

---

## What is already strong (do not touch)

- Homepage Organization + Person JSON-LD: `legalName`, `foundingDate`,
  `founder`, 6-item `sameAs`. Correctly anchored to `#organization`.
- Content quality: filler 0/100, AI-pattern 0/100, density 1.00. This copy is
  human and specific — rewriting it for "SEO" would destroy the signal.
- Static HTML, no SPA: `agentic_check` P0 pass on no-JS readability.
- Security headers: HSTS preload, CSP, X-Frame-Options DENY, nosniff.
- Real 404 with `noindex` (not a soft 404).
- `Googlebot` (search indexing) is **not** blocked — classic SEO is unaffected
  by the AI-crawler blocks.

---

## Recent Google updates to be aware of
(pulled live via `seo_updates.py`, verified 2026-09-28)

- **Sept 2026 Spam Update** (global, all languages, started 09-24, up to two
  weeks). No named target — standard hygiene applies.
- **Preferred sources in AI features** now require inclusion in the Search
  generative AI control in Search Console. Relevant if AI Overview presence is
  a goal — pairs with the `llms.txt` + `robots.txt` recommendations.
- **VideoObject** now documents `creator` (Person/Organization) and expanded
  `interactionStatistic` — relevant if video is added later.

---

## Artifacts

- `audit-data.json` — structured envelope (drives the PDF report)
- `findings/technical.md`, `content.md`, `onpage.md`, `schema.md`,
  `performance.md`, `ai-readiness.md`, `images.md`
- `ACTION-PLAN.md` — prioritized roadmap
- `alieninc.tech-full-audit.pdf` — generated via `google_report.py`
