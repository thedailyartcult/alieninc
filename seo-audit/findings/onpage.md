# On-Page SEO Findings — alieninc.tech

## What works

- Homepage title: `Alien Inc. – Guardian of Philippine Digital Infrastructure` — clear, branded, ~52 chars.
- Homepage has canonical + OG + Twitter Card + Organization JSON-LD.
- Single H1 on homepage (correct hierarchy).
- `about.html` has OG + Twitter + description.

## Findings

### Medium — 115 pages missing Open Graph / Twitter Card
Crawl of 357 URLs: 115 have no `og:title`. Same set lacks Twitter Card.
These pages will render with an unpredictable preview on LinkedIn, X,
Facebook, and WhatsApp — a real distribution cost for a corporate group that
publishes articles.

**Fix:** add `og:type`, `og:url`, `og:title`, `og:description`, `og:image`,
`twitter:card` site-wide. `tools/inject-seo.py` already emits exactly this
pack for the 8 subdomain roots — the gap is everything else.

### Low — `logo.png` uses `alt="•"` on every page
Found on homepage, founder.html, about.html. A bullet is not a valid alt
value: it fails WCAG (a "•" is announced as "bullet" by screen readers) and
wastes an image-SEO signal on the brand logo.

**Fix:** either `alt="Alien Inc"` (if the logo is the sole link to home and
needs a name) or `alt=""` with `role="presentation"` (if decorative and the
link already has `aria-label`, which it does: `aria-label="visit the Alien
Inc Homepage"`). The correct choice here is **`alt=""`** because the brand
link already carries an accessible name.

### Info — founder.html is a thin on-page target
`founder.html` has no meta description, no OG, no Twitter Card, yet it is
linked from Organization `sameAs` and is a primary E-E-A-T surface.
Priority page for the description pass.
