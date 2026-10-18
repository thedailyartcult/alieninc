# Schema / Structured Data Findings — alieninc.tech

Validator: `parse_html.py` + `fetch_page.py` (JSON-LD block extraction), sample
of 80 crawled pages.

## Homepage Organization block — valid

```json
{
  "@type": "Organization",
  "@id": "https://alieninc.tech/#organization",
  "name": "Alien Inc",
  "alternateName": "Alien.Inc",
  "legalName": "Alien Incorporated",
  "url": "https://alieninc.tech",
  "email": "founder@alieninc.tech",
  "foundingDate": "2016-12-22",
  "founder": { "@type": "Person", "name": "Patrick Neil Alcantara", ... },
  "sameAs": [ 6 profiles ]
}
```

3,160 bytes, 1 block, `valid: true`, types `[Organization, Person, ...]`.

**Assessment:** this is a well-formed Organization + Person graph. The `@id`
anchors correctly to `#organization`, `legalName` is present (Google uses it
for knowledge-panel entity matching), and `sameAs` points to real, owned
profiles. No fix needed.

## Crawl-wide schema distribution (sampled pages)

| @type | count |
|---|---|
| WebPage | 38 |
| Organization | 4 |
| AboutPage | 1 |

## Findings

### Low — 110 pages have no structured data
Article pages under `/articles/`, most `panteon.alieninc.tech` product pages,
and the subdirectory portals carry no JSON-LD. Given the strong homepage
graph, the gap is at page level.

**Fix, in priority order:**
1. `WebSite` schema on the homepage (with `SearchAction` if a search exists).
2. `Article` + `author` (linking to the founder `#person` `@id`) on `/articles/*`.
3. `BreadcrumbList` on nested pages — cheap, and it earns breadcrumb rich results.

### Note — FAQ/QAPage context changed in 2026
Per the bundled `schema_generate.py` reference and the September 2026 Google
changelog, FAQ rich results are restricted. Do not invest in FAQPage markup
expecting rich results; use it only if you have genuine on-page Q&A.
