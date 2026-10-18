# Content Quality Findings — alieninc.tech

Scorer: `content_quality.py` (QRG-aligned, v2.4.0), run on homepage HTML.

## Homepage score: 96/100

| Metric | Value |
|---|---|
| Overall quality | 96/100 |
| Filler score | 0/100 (higher = worse) |
| AI-pattern score | 0/100 (higher = worse) |
| Information density | 1.00 |
| Repetition | 24/100 (higher = worse) |
| Tokens | 21,098 (3,247 unique) |

**Interpretation:** the homepage copy is strong. Zero filler, zero AI-pattern
detection, full information density. Repetition at 24/100 is mild and expected
for a brand page that repeats the company name. This is the strongest category
on the site — do not rewrite it.

## Word count / structure

- Word count: 868
- H1: 1 (`Sovereign Continuity Infrastructure for the Next Thousand Years.`)
- H2: 6 — Company Directory, Sitemap, Where The Network Operates, COMPANY PROFILE, etc.
- H3: 7 — Domain-to-Platform, Intel-to-Decision, Risk-to-Product, Trust & Compliance, Group, Simulation Stack, plus one narrative line

## E-E-A-T signals (strong)

- Founder named in visible copy AND in Organization JSON-LD (`founder: Patrick Neil Alcantara`)
- `foundingDate: 2016-12-22`, `legalName: Alien Incorporated` — verifiable entity facts
- Compliance frameworks cited (CIS, DISA, PCI-DSS, OWASP, NIST, GDPR, SOC2, ISO27001…)
- `sameAs` points to 6 real profiles (LinkedIn, Instagram, Facebook, art subdomain, founder page)

## Findings

### High — 112 pages have no meta description
31% of the 357 sitemap URLs return no `<meta name="description">`. Google will
auto-generate snippets, which usually underperform hand-written ones for CTR.

**Fix:** write 120–155 char descriptions for every key page. The pattern already
exists in `tools/inject-seo.py` — extend it beyond the 8 subdomain roots.

### Medium — 46 pages have no H1
Concentrated on `panteon.alieninc.tech` subpages: `yono-forge.html`,
`pipeline-builder.html`, `capabilities/arsenal.html`, and the
`platforms/cmb/pages/*` set (analytics, dashboard, history, status, workspaces).

**Fix:** one unique H1 per page. These pages likely have `<h2>` as their visual
title — demote/restructure to H1.

## Claim-citation note
`content_verify.py` (claim + citation-gap detector) is designed for drafts.
Homepage claims (founding date, compliance frameworks, sameAs URLs) are
concrete and verifiable; no citation gaps flagged.
