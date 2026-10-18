# Action Plan — alieninc.tech

Prioritized by (impact × inverse effort). Generated 2026-10-18 by
claude-seo v2.4.0.

---

## Phase 1: Critical fixes — Week 1

| # | Item | Why | How |
|---|---|---|---|
| 1 | **Publish `/llms.txt`** | Currently 404. Lighthouse drops the agentic audit from its fraction; a valid file adds a counted pass and creates an AI-answer surface for all 7 portals. | New file at repo root, H1 + `>` summary + markdown links. Content drafted in `findings/ai-readiness.md`. |
| 2 | **Resolve the AI-crawler robots.txt policy** | The site declares AI readiness (`Content-Signal`, WebMCP) yet blocks 10 AI crawlers. Blocking `Google-Extended` directly suppresses AI Overview visibility. **This is a strategy decision — surface it to the founder, do not decide unilaterally.** | If GEO is a goal: unblock `Google-Extended` + `PerplexityBot`. Keep `GPTBot`/`CCBot`/`Bytespider` blocked to stay out of training corpora. `Googlebot` is already unblocked, so classic SEO is unaffected either way. |
| 3 | **Fix the sitemap 404** | `https://alieninc.tech/trust/index.html` is listed in `sitemap.xml` but returns 404. Crawl-budget and quality signal. | Remove the `<url>` entry, or restore the page (the homepage `compliance` meta tag points at `report=/trust/`). |
| 4 | **Fix `logo.png` alt + dimensions** | `alt="•"` fails WCAG 1.1.1 and wastes the brand image signal. Missing `width`/`height` risks CLS. | `alt=""` (decorative — the brand link already has `aria-label`), plus intrinsic `width`/`height`. |

---

## Phase 2: High-impact improvements — Weeks 2–3

| # | Item | Scope | How |
|---|---|---|---|
| 5 | **Meta descriptions** | 112 pages | 120–155 chars each. `tools/inject-seo.py` already has the pattern for 8 subdomain roots — extend it to all subpages, or emit at build time. |
| 6 | **Canonical tags** | 120 pages | Self-referencing `<link rel="canonical">` everywhere. Same tooling as #5. |
| 7 | **Open Graph + Twitter Card** | 115 pages | `og:type/url/title/description/image` + `twitter:card`. Same tooling. Priority: `founder.html` (primary E-E-A-T surface, currently bare). |
| 8 | **H1 tags** | 46 pages | Mostly `panteon.alieninc.tech`: `yono-forge`, `pipeline-builder`, `capabilities/arsenal`, `platforms/cmb/pages/*`. Promote the visual title from H2 → H1. |
| 9 | **Canonicalize duplicate titles** | 2 pairs | `articles/2026/09/24/The-Alien-Minds-We-Built.html` vs its `index.html`; `panteon login.html` vs `secure.alieninc.tech`. Prefer the pretty URL. |

**Recommended approach for #5–#7:** do not hand-edit 200+ HTML files. Either
(a) extend `tools/inject-seo.py` from 8 roots to all pages, or (b) add a small
build-time templating step. Option (a) is lower-risk and matches the existing
repo convention.

---

## Phase 3: Content & authority — Month 2

| # | Item | Why |
|---|---|---|
| 10 | **`WebSite` + `Article` + `BreadcrumbList` schema** | 110 pages have no JSON-LD. `Article` with `author` → the founder `#person` `@id` strengthens E-E-A-T on the articles hub. |
| 11 | **Configure `GOOGLE_API_KEY` for CrUX/PSI** | Turns Performance from inference into measured p75 LCP/INP/CLS. Without it, CWV stays unmeasured. |
| 12 | **Enable Cloudflare HTML cache** | `cf-cache-status: DYNAMIC` means the homepage HTML is never edge-cached despite `max-age=600`. Add a Cache Rule for `alieninc.tech/*`, with `Bypass Cache on Cookie` for `trust/`, `dashboard.html`, and any auth'd routes. |
| 13 | **Self-host the three Google Fonts** | Ultra, Alfa Slab One, Instrument Sans are render-blocking third-party requests. Self-hosting removes the dependency and is consistent with the strict CSP. |
| 14 | **Consider `ai-catalog.json` + A2A agent card** | Optional. Relevant if Panteon-as-a-product wants agent discoverability; not urgent for the corporate umbrella site. |

---

## Phase 4: Monitoring & iteration — Ongoing

| # | Cadence | Command |
|---|---|---|
| 15 | Monthly | `agentic_check.py https://alieninc.tech` — track readiness score against the P0/P1/P2/P3 baseline in this audit |
| 16 | After each deploy | Re-crawl `sitemap.xml` and check status codes + meta coverage — `consistency_check.py` on the repo for dead refs/orphans |
| 17 | Monthly | `seo_updates.py --limit 10` — primary-source Google updates changelog (Sept 2026 Spam Update still relevant) |

---

## Explicitly do NOT do

- **Do not rewrite the homepage copy.** It scores 96/100 with 0 filler and 0
  AI-pattern detection. "Optimizing" it would destroy the strongest signal on
  the site.
- **Do not add FAQPage schema expecting rich results.** FAQ rich results are
  restricted as of 2026; use only for genuine on-page Q&A.
- **Do not unblock `GPTBot`/`CCBot`/`Bytespider` without a deliberate decision.**
  These are training crawlers, not answer engines. The GEO-relevant ones are
  `Google-Extended` and `PerplexityBot`.
- **Do not hand-edit 200+ HTML files** for the meta/canonical/OG pass — extend
  the existing `tools/inject-seo.py` pattern instead.
