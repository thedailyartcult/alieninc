# Platforms — AGENTS.md

## This folder contains product pages for the Five Elements domains

`index.html` is the Platform Directory — a homepage-design-language landing page (self-contained, mirrors `../index.html` style/scripts) that catalogs every product grouped by the Five Elements domains: Terra (YONO, Terranean Etiology, Terranean Teleology), Abyss (Crackerbox), Stratos (Statham), Cosmos (Spinal Craker), Cyber (CMB). All paths are `../`-prefixed to resolve from this folder.

Each product page follows the unified Panteon design language. Use `../platform-template.html` as the starting point.

## Existing Products

| File | Domain | Product |
|------|--------|---------|
| `crackerboxpalace.html` | Flagship (CBP) | Crackerbox Palace — the integrated stack (Spinal Craker + Crackerbox + YONO) |
| `yono.html` | Terra (Land) | YONO — AI Operations Platform |
| `crackerbox.html` | Abyss (Sea) | Crackerbox |
| `terranean-etiology.html` | Terra | Terranean Etiology — Causal Forensics |
| `terranean-teleology.html` | Terra | Terranean Teleology — Purpose Modeling |
| `statham.html` | Stratos (Air) | Statham |
| `spinal-craker.html` | Cosmos (Space) | Spinal Craker |
| `cmb-product.html` | Cosmos | CMB — Persistent Memory (internal tooling) |

## Platform Nav Groups

Products within the same domain share a `.platform-nav` bar:

- **Terra products**: yono.html, terranean-etiology.html, terranean-teleology.html
- **Cosmos products**: cmb-product.html, statham.html, crackerbox.html, spinal-craker.html, yono.html

When adding a new product page, update the sibling nav links on related pages.

## Page Structure (mandatory)

1. `<link rel="stylesheet" href="../styles.css">` — always relative path
2. Google Fonts Inter import (only font allowed)
3. Inline `<style>` for page-specific overrides (platform-hero, architecture-grid, etc.)
4. SVG brand lockup (single-source, inline)
5. Announcement bar → Header → Platform Hero → Main Content → Footer
6. Scroll-handler script at bottom

Media paths on product pages MUST be `../`-prefixed (`../hero-bg-panteon.mp4`, `../panteon-software.png`) — those assets live in `panteon/`, one level above `platforms/`. A bare `hero-bg-panteon.mp4` resolves into `platforms/` and 404s.

## Content Sections (in order)

1. **Platform Hero**: tag, headline (2 lines max), description (1-2 sentences), CTA arrow
2. **Platform Nav**: horizontal tabs linking to sibling products
3. **Prose Section** (`#overview`): heading + 2-4 paragraphs explaining the product
4. **Core Capabilities**: 2x2 grid of `.architecture-card` with `/01`, `/02`, `/03`, `/04` tags
5. **Editorial Callout**: single impactful statement
6. **How It Works**: 3-step workflow with step-num, text, and media placeholder
7. **CTA Section**: centered heading + description + button

## CMB Product Page Note

`cmb-product.html` describes CMB (Cosmic Microwave Background), an internal memory tool for Alien Inc's six companies. It is NOT commercial software. The page should:
- Use the standard platform template structure
- Note that it's internal tooling in the tag line (e.g., "Cosmos Domain · CMB")
- Link to the dashboard at `../cmb/`
- NOT expose internal API paths, element IDs, or technical contract details
- Keep the description at a product level, not an implementation level

## Forbidden

- NO new fonts, colors, or layouts
- NO different footer or header structures
- NO commercial language for CMB (it's internal)
- NO exposing internal technical details in product descriptions

## Terranean Procedural Terrain Exception

`terranean-etiology.html` and `terranean-teleology.html` are the **sole** pages permitted to load a third-party JS library (`three.js r128` via `cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js` with `../vendor/three.r128.min.js` fallback) for the Mt. Bullagao procedural canvas (`#webgl-bg-canvas`). Rules:

- Canvas is `position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:0; pointer-events:none` **fixed global** behind all content (`main.main-content` and sections are `background:transparent` with white glass `rgba(255,255,255,0.88) blur` to reveal it), like `../index.html`’s `#subterranean-bg-canvas`. This whole-site cover was requested to match the homepage background behavior.
- Uses only Panteon tokens (`--accent-neon:#DFF140`, `--bg-dark:#000000`, `--bg-light:#ffffff` with white glass). No HUD/telemetry overlays, no glass-header overrides, no new colors/fonts.
- Must include `@media (prefers-reduced-motion:reduce)` fallback (hide canvas) and `document.hidden` guard with `requestAnimationFrame` pause.
- All other platform pages remain vanilla-JS only.

---

## Admin Console Decomposition (2026-08-31) — Operational Rigor

This directory now ALSO holds the admin console lazy platforms (separate from marketing product pages above). Do not confuse the two.

Admin decomposition:
- `registry.json` — single source of truth for shell lazy loading (sidebar + router). Shell `admin.html` fetches `/static/platforms/registry.json` on first navigate.
- `{id}/nav.json` — sidebar metadata for one admin platform (NOT the marketing nav).
- `{id}/manifest.json` — version, apiDependencies, budgets (maxLines 900 / maxTokens 16000).
- `{id}/pages/*.html` — extracted `div.page` fragments from admin.html (lazy-fetched via `/static/platforms/{id}/pages/{page}.html`). Inline fallback remains in admin.html so no functionality is lost.
- `{id}/module.js` — platform JS placeholder (future: move load* handlers here). Loader injects via `/static/platforms/{id}/module.js` on first navigate.
- `shared/api.js`, `shared/design-tokens.md` — cross-platform contracts.

Cohesive panel guarantee: admin.html still renders all nav/pages inline as fallback; loader (`ensurePageFragment` + `ensurePlatformModule`patched into async navigate at admin.html:5561) falls back silently if fetch fails — zero functional loss.

LLM focus protocol (different context windows):
1. Read `registry.json` (1k tokens)
2. Read `platforms/{id}/manifest.json` + `nav.json`
3. Read only that platforms `pages/*.html` + `module.js`
Total < 25k fits 32k windows. Do NOT read other platforms or whole admin.html (26192 lines / 1.5M). Use `scripts/check-platform-budgets.sh` in CI.

Next steps: move YONO handlers, then Spinal Cracker fusion (2289 lines), then delete inline duplicates after one release of dual fallback.
