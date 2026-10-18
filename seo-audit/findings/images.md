# Image SEO Findings — alieninc.tech

## Scope
Homepage + founder.html + about.html inspected; image inventory is small.

| Page | Images | Bad alt |
|---|---|---|
| `/` | 1 | `logo.png` |
| `/founder.html` | 2 | `logo.png` |
| `/about.html` | 1 | `logo.png` |

## Findings

### Low — `logo.png` has `alt="•"` on every page
The brand logo uses a bullet character as alt text. Two problems:

1. **Accessibility (WCAG 1.1.1).** Screen readers announce "bullet" where the
   brand name should be, or skip it awkwardly.
2. **Wasted image-SEO signal.** The logo is the most-linked brand asset on the
   site; a meaningful alt is free entity reinforcement.

**Correct fix:** the brand link already carries an accessible name
(`aria-label="visit the Alien Inc Homepage"` on `index.html`), so the logo is
**decorative** in that context. Use:

```html
<img src="logo.png" alt="">
```

Empty alt is the correct value for a decorative image inside an already-labelled
link. Do **not** set `alt="Alien Inc"` here — that would duplicate the link's
accessible name and cause "Alien Inc, visit the Alien Inc Homepage" verbosity.

### Info — no width/height attributes
Parsed `logo.png` has `width: null, height: null`. Without explicit dimensions,
browsers cannot reserve layout space, which risks **Cumulative Layout Shift**
when the image loads.

**Fix:** add intrinsic `width`/`height` attributes (or CSS `aspect-ratio`) to
every `<img>`. Cheap CLS win that does not require measuring CWV first.

### Info — very low image count
One image on the homepage is a strength for payload/LCP. There is no
image-optimization debt (no oversized hero JPEGs, no unconverted PNG galleries)
on the main pages. The `ai.jpeg` / `ai.original.jpeg` pair at the repo root
suggests an original was kept — ensure only the compressed derivative is
served.
