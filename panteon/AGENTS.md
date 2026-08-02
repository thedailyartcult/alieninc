# Panteon Design Language — AGENTS.md

## CRITICAL: DO NOT invent new design patterns

Every HTML page in this directory tree MUST follow the established Panteon design language. Do NOT create new fonts, colors, layouts, or component patterns. Use what already exists.

## Design Tokens (from styles.css)

```css
--bg-dark: #070809;
--bg-light: #ffffff;
--bg-gray: #f4f4f6;
--text-dark: #111213;
--text-light: #ffffff;
--text-muted: #707275;
--border-light: rgba(255, 255, 255, 0.1);
--border-dark: rgba(0, 0, 0, 0.08);
--font-sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
```

## Typography

- **Only** Google Fonts Inter (weights 300, 400, 500, 600, 700)
- **Never** import other fonts
- Hero headlines: `font-weight: 300`, `letter-spacing: -0.03em`
- Body text: `font-size: 0.95rem–1.15rem`, `line-height: 1.55–1.75`
- Tags/labels: `font-family: var(--font-mono)`, `font-size: 0.7rem`, `text-transform: uppercase`

## Page Structure (all product/capability/article pages)

1. SVG brand lockup (single-source, inline `<defs>`)
2. Announcement bar (`.announcement-bar`)
3. Header (`<header id="main-header">`) with logo + nav-right
4. Hero section (`.platform-hero` with video bg)
5. Main content (`.main-content`) — white/light background
6. Footer (identical across ALL pages)
7. Scroll-handler script at bottom

## Required Components

- **Platform Hero**: `.platform-hero` with `.platform-hero-bg` video, `.platform-hero-content`
- **Platform Nav**: `.platform-nav` horizontal tab bar for sibling pages
- **Architecture Grid**: `.architecture-grid` (2-column) with `.architecture-card`
- **Prose Section**: `.prose-section` for overview text (max-width 800px)
- **Workflow Steps**: `.workflow-steps` with `.workflow-step` (3-column: num, text, media)
- **Editorial Callout**: `.editorial-callout` with `.editorial-callout-text`
- **CTA Section**: centered heading + description + button

## CSS File

- All pages link to `../styles.css` (relative path from subdirectory)
- Page-specific styles go in `<style>` block in `<head>`
- The shared `styles.css` contains: reset, tokens, header, footer, cards, sections, responsive

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

Logo usage: `<a href="../index.html" class="logo"><svg viewBox="0 0 295 100"><use href="#panteon-lockup"/></svg></a>`

## Responsive Breakpoints

- `1024px`: grids collapse to fewer columns
- `768px`: mobile padding (24px), hero padding reduced

## Template

Use `../platform-template.html` as the starting point for any new product, capability, or article page. Replace `{{PLACEHOLDER}}` tokens with actual content.

## Forbidden

- NO Tailwind, Bootstrap, or CSS frameworks
- NO new font imports
- NO new color values (use CSS variables)
- NO different footer structures
- NO different header structures
- NO inline styles that override the design system (except for one-off CTA button variants)
- NO emoji in UI text
- NO third-party JS libraries (only the scroll-handler script)

## CMB Dashboard Exception

The `cmb/cmb.html` file is the internal application dashboard (not a marketing page). It has its own design system with 4 themes (slate, midnight, paper, matrix), sidebar navigation, and complex data visualization. This is intentional and should NOT be changed to match the marketing page template. The `cmb-product.html` page in the platforms folder IS the marketing/product description page and DOES follow the template.
