# Panteon Design Language — AGENTS.md

## CRITICAL: DO NOT invent new design patterns

Every HTML page in this directory tree MUST follow the established Panteon design language. Do NOT create new fonts, colors, layouts, or component patterns. Use what already exists.

**The homepage (`index.html`) is the canonical design language reference.** It was redesigned 2026-08-10 and is fully self-contained (inline `<style>` block + one inline script). When in doubt, open `index.html` and match it.

## Design Tokens (from index.html `:root`)

```css
--bg-dark: #000000;
--bg-light: #ffffff;
--bg-gray: #f8f9fa;
--text-dark: #000000;
--text-light: #ffffff;
--text-muted: #71717a;
--accent-neon: #DFF140; /* Yellow-Green Neon accent */
--border-light: rgba(255, 255, 255, 0.15);
--border-dark: #000000;
--border-subtle: rgba(0, 0, 0, 0.12);
--font-sans: "Inter", -apple-system, sans-serif;
--font-tech: "Space Grotesk", monospace;
--font-mono: "JetBrains Mono", monospace;
--font-brand: "Inter", -apple-system, sans-serif;
```

Note: the body background is `var(--bg-dark)` (#000000) — the homepage is a **dark theme** page; light surfaces (`.main-content`) sit on top.

## Typography

- **Only** Google Fonts: Inter (300–700), Space Grotesk (300–700, `--font-tech`), JetBrains Mono (300–600, `--font-mono`)
- **Never** import other fonts
- Headlines/section titles use `--font-tech` (Space Grotesk), `font-weight: 300`
- Body text: `--font-sans` (Inter), `line-height: 1.5–1.75`
- Tags/labels (`.section-badge`, press tag, eyebrow text): `font-family: var(--font-mono)`, `text-transform: uppercase`, small size

## Homepage Structure (`index.html`)

1. Inline `<defs>` brand lockup SVG (`.panteon-lockup` referenced via `#panteon-lockup`)
2. `<head>` inline `<style>` (reset, tokens, all section styles) + font import
3. `dimension-transition-overlay` (`#dim-overlay`) — entrance reveal with grid lines
4. `scroll-progress-bar` (`#scroll-bar`) — fixed neon top progress bar
5. `.announcement-bar` (`#top-announcement`) — top ribbon
6. `header#main-header` — sticky glass header + logo + nav, with `mega-menu-overlay` and `.mega-menu-container` panels (`#menu-five-elements`, `#menu-capabilities`, `#menu-company`) + `#mobile-drawer-overlay`
7. `.hero` with `hero-video-bg` (hero-bg-panteon.mp4) + `.hero-content` (hero-title with `.reveal-text-line`, `.scroll-explore-tag`, `.hero-arrow`)
8. `<main class="main-content" id="scroll-content">` — the sections below
9. Footer `<footer id="footer">` — `.footer-container` with left branding (logo, copyright, cookies button, `.footer-social-container`), `.footer-links-grid` of `.footer-links-col` accordions
10. One inline `<script>` block at the bottom with the interaction engines

## Section Components (in order on the homepage)

- **Use Cases marquee**: `.alien-use-cases-section` → `.section-header-bar` (title + `.section-badge`) + `.use-cases-track-container#use-cases-container` → `.use-cases-track-wrapper#use-cases-track` containing `.use-case-card` items
- **Partners gliding marquee**: `.partners-section` → `.partners-header` + `.partners-marquee-container#partners-container` → `.partners-marquee-track#partners-track` containing `.partner-box` items (180×180 linked boxes; anchors need `text-decoration: none`)
- **User Segments**: `.user-segments-section` → `.user-segments-grid` with `.user-segment-col` (2 columns)
- **Editorial Callout**: `.editorial-callout` with `.editorial-callout-text.reveal-text-line`
- **Software Grid**: `.software-section` → `.software-header` + `.software-grid-matrix` containing `.software-card` items (last card uses `style="grid-column: span 2;"`)
- **Press Coverage**: `.press-section` → `.press-header-tag` + `.press-list` of `.press-item` (each with `data-preview` image attribute, `.press-title`, `.press-discover`), plus `#press-floating-card` floating hover preview
- **Pre-footer Contact**: `.pre-footer-contact` with `#spiralCanvas` (canvas) + `.pre-footer-content`
- **Section header pattern**: `.section-header-bar` / `.partners-header` with `.reveal-text-line` heading + `.section-badge` (mono, uppercase)

## CSS File

- The homepage (`index.html`) is **self-contained**: all styles live in one inline `<style>` block in `<head>`. Do not split it out.
- Product/capability/article subpages still link to `../styles.css` (shared tokens, header, footer, cards) with page-specific `<style>` in `<head>`.
- Keep the design tokens identical wherever a page defines its own `:root`.

## Interactive Systems (bottom inline `<script>`)

1. Dimension switch entrance reveal (`#dim-overlay`)
2. Header scroll + parallax engine (`data-parallax-bg`, `data-parallax-content`, `data-parallax-item`, `.reveal-text-line` via IntersectionObserver)
3. Continuous gliding track engine (`createContinuousTrack(containerId, trackId, speed)` — clones children, auto-scroll, drag/touch support) — used for use-cases and partners
4. Mega menu controller (`.nav-item-dropdown` + `#mega-menu-overlay` + mobile drawer)
5. Floating press image preview (`#press-floating-card` + `.press-item` hover)
6. High-DPI 3D perspective vector canvas engine (`#spiralCanvas`)
7. Footer accordions on mobile (`.footer-links-col h4` click toggle)

## Brand SVG

Every page MUST include the single-source brand lockup SVG:
```html
<svg aria-hidden="true" width="0" height="0" style="position:absolute;overflow:hidden">
    <defs>
        <filter id="panteon-brush">...</filter>
        <mask id="panteon-roll">...</mask>
        <g id="panteon-lockup" fill="currentColor">...</g>
    </defs>
</svg>
```

Logo usage (homepage, click scrolls to top): `<svg viewBox="0 0 295 100" role="img" aria-label="Panteon"><use href="#panteon-lockup"/></svg>`

## Responsive Breakpoints

- `1200px`: grids collapse to fewer columns
- `768px`: mobile padding (24px), hero padding reduced, footer columns become accordions

## Template

Use `../platform-template.html` as the starting point for any new product, capability, or article subpage. For new homepage-style landing sections, copy the matching section from `index.html` directly.

## Forbidden

- NO Tailwind, Bootstrap, or CSS frameworks
- NO fonts other than Inter, Space Grotesk, JetBrains Mono
- NO new color values (use the CSS variables above)
- NO different footer structures
- NO different header structures
- NO emoji in UI text
- NO third-party JS libraries (all interaction engines are inline vanilla JS)
- NO inline `style=""` attributes that override the design system (the only sanctioned one is the `grid-column: span 2` software card)

## CMB Dashboard Exception

The `cmb/cmb.html` file is the internal application dashboard (not a marketing page). It has its own design system ("Command Deck") and should NOT be changed to match the marketing page template. The `cmb-product.html` page in the platforms folder IS the marketing/product description page and DOES follow the template.

Command Deck design language (self-contained, one inline `<style>` + 4 inline `<script>` blocks including d3 v7.9.0 and a force-graph bundle):
- Layout: sticky top `.deck` (brand lockup, 6-item `.deck-nav` with `data-view` buttons, workspace chip, theme select, `.engine-status` dot) over `<main>` containing six `.view` panels keyed by `data-view-panel`: today, ask, library, relations, manage, provenance.
- Dark-first design: `--bg:#05060a`, lime accent `--accent:#DFF140`, fonts Inter / Space Grotesk / JetBrains Mono.
- 4 themes via `body[data-theme]`: slate (default), midnight, paper, matrix. Theme select is `#theme-select`.
- Graph studio (relations view): `.relations-layout` = sticky `.graph-stage` (`.graph-canvas` with `data-graph-style` backgrounds galaxy/solar/classic) + 380px `.graph-rail` (`.graph-tabs` analyse/explore/time, search, toolbars, style/layout/palette presets via `data-graph-*-choice` chips, motion switches, saved views `data-graph-saved-view`, `<details class="graph-tuning">` with `graph-layer-chip` chips for `data-graph-layer` temporal/entity/causal/semantic/code).
- Editable structure: the front-end ends at the first `<script>` (d3 bundle); assembly = front + scripts region. Contract for edits: every `byId(...)` id referenced in the scripts must exist as static HTML in the front or be generated at runtime by the render helpers (automation/LLM settings, graph-connections dialog).
- Ask view: `#answer-panel` + `<details class="retrieval-details">` → `#retrieval-list` (raw /recall candidates).

## Research Institute

The `research/` folder has been renamed to `panteon-research-institute/`. It contains:
- `index.html` — auto-generated article landing page
- `mission-and-vision.html` — founding charter
- `publish.py` — zero-dependency article publisher
- `source/` — drop `.md` files here to publish
- `articles/` — generated HTML (do not hand-edit)

All links to the research institute now point to `panteon-research-institute/index.html`.
