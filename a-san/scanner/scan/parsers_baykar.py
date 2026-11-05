"""Parser for baykartech.com — Baykar (Turkish UAV manufacturer) product pages.

Direct-manufacturer source (same trust pattern as milremrobotics.com): the
specs printed on the page come from the OEM itself. robots.txt allows
User-agent:* except /super/*; EN sitemap at https://baykartech.com/en/sitemap.xml
lists /en/uav/<slug>/ product pages. © Baykar — fact extraction with attribution.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "baykartech.com"


def parse_baykar_product(url: str, html: str) -> CatalogEntry | None:
    """Parse a baykartech.com/en/uav/<slug>/ product page."""
    if not html:
        return None

    # Designation: og:title or H1 ("Bayraktar TB2").
    name = ""
    og_m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html, re.I)
    if not og_m:
        og_m = re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"', html, re.I)
    if og_m:
        name = html_lib.unescape(og_m.group(1)).strip()
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", name)).strip()
    if not name:
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
        if h1_m:
            name = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).strip()
        name = re.sub(r"\s+", " ", name)
    if not name:
        return None

    # Spec sheet: label spans followed by value spans, e.g.
    #   <span ...>Length</span><span class="value">6.4 m</span>
    specs: list[str] = []
    seen_labels: set[str] = set()
    pair_re = re.compile(
        r'<span[^>]*>\s*([A-Z][A-Za-z0-9 ()/\-]{2,40})\s*</span>\s*'
        r'<span[^>]*class="[^"]*\bvalue\b[^"]*"[^>]*>(.*?)</span>', re.S)
    for m in pair_re.finditer(html):
        label = re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip()
        value = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        key = label.lower()
        if label and value and key not in seen_labels and len(value) <= 120:
            seen_labels.add(key)
            specs.append(f"{label}: {value}")

    # Description: meta description or first substantive paragraph.
    desc = ""
    dm = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html, re.I)
    if not dm:
        dm = re.search(r'<meta[^>]+content="([^"]*)"[^>]+name="description"', html, re.I)
    if dm:
        desc = re.sub(r"\s+", " ", html_lib.unescape(dm.group(1))).strip()

    return CatalogEntry(
        designation=name,
        category="UAVs",
        country="Turkey",
        manufacturer="Baykar",
        description=desc[:600] or f"{name} — manufacturer fact sheet (Baykar).",
        specs=specs[:24],
        sources=[SourceRef("Baykar (manufacturer)", url)],
        fetched_at=now_iso(),
    )
