"""Parser for rheinmetall.com — Rheinmetall AG (German defense prime).

robots.txt: User-agent:* allow-all except job-ad paths and utm_source=Sailthru
parameters. No crawl-delay. Sitemap: /sitemap.site_1.xml.
Content licence: © Rheinmetall AG — fact-extraction with attribution
(see POLICY.md): designation + description + exact source URL; the product
pages carry marketing prose, not spec tables, so specs are usually empty.

Product pages are server-rendered Tailwind HTML:
  <title>Mission Master – Uncrewed Ground Vehicles family (UGV) | Rheinmetall</title>
  <h2>Mission Master SP2</h2> (variant sections on family pages)
  meta name="description" carries a clean summary.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.rheinmetall.com"

# Curated robots-allowed EN product URLs (verified in sitemap.site_1.xml,
# 2026-08-25). Facility pages and non-defense products are excluded.
RHEINMETALL_PRODUCT_URLS: list[tuple[str, str]] = [
    ("https://www.rheinmetall.com/en/products/uncrewed-systems-and-autonomous-navigation-technology/mission-master-a-ugs",
     "UGVs"),
    ("https://www.rheinmetall.com/en/products/uncrewed-systems-and-autonomous-navigation-technology/axus-autonomous-vehicle",
     "UGVs"),
    ("https://www.rheinmetall.com/en/products/uncrewed-systems-and-autonomous-navigation-technology/komodo",
     "UGVs"),
    ("https://www.rheinmetall.com/en/products/uncrewed-systems-and-autonomous-navigation-technology/luna-uncrewed-air-supported-reconnaissance-system",
     "UAVs"),
]


def parse_rheinmetall(url: str, html: str,
                      category_display: str = "UGVs") -> CatalogEntry | None:
    """Parse a rheinmetall.com EN product page."""
    if not html:
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
    # "Mission Master – ... | Rheinmetall" -> drop the "| Rheinmetall" suffix
    name = re.split(r"\s*\|\s*", title)[0].strip()
    # Long en-dash descriptors ("AXUS – A modular, multi-purpose autonomous
    # vehicle") are trimmed to the short designation and kept as an alt name.
    alt_descriptor = ""
    dash_m = re.match(r"^([A-Za-z0-9\- ]{2,30}?)\s+[–—]\s+(.+)$", name)
    if dash_m:
        alt_descriptor = name
        name = dash_m.group(1).strip()
    else:
        # Collapse the family-page form "Mission Master – Uncrewed Ground
        # Vehicles family (UGV)" to a compact designation.
        name = re.sub(r"\s*[–—]\s*Uncrewed\s+.*$", "", name,
                      flags=re.I).strip() or name
    if not name:
        return None

    # Description: meta description, then variant H2s as alt names.
    desc = ""
    meta_m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if meta_m:
        desc = html_lib.unescape(meta_m.group(1)).strip()

    variants: list[str] = []
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    for h in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S | re.I):
        cand = re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<[^>]+>", "", h))).strip()
        if cand.startswith(name.split()[0]) and cand != name and len(cand) < 60:
            variants.append(cand)

    if not desc:
        paras = re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I)
        for p in paras:
            text = re.sub(r"\s+", " ", html_lib.unescape(
                re.sub(r"<[^>]+>", "", p))).strip()
            if len(text) > 80:
                desc = text
                break
    if not desc:
        desc = f"Rheinmetall product: {name}"
    if variants:
        desc = f"{desc} Variants: {', '.join(variants[:4])}."

    return CatalogEntry(
        designation=name,
        alt_names=([alt_descriptor] if alt_descriptor else []) + variants[:6],
        country="Germany",
        manufacturer="Rheinmetall",
        category=category_display,
        description=desc[:500],
        specs=[],
        sources=[SourceRef("Rheinmetall", url)],
        fetched_at=now_iso(),
    )
