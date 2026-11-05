"""Parser for qinetiq.com — QinetiQ robotic products (UK).

robots.txt: User-agent:* allow-all except one hashed page and *.pdf;
Crawl-delay: 1 (below our default 1.5s, so no HOST_CRAWL_DELAY override).
Content licence: © QinetiQ — fact-extraction with attribution (see POLICY.md):
designation + description + exact source URL. Pages are prose-only (no spec
tables in served HTML); <title> is SEO-generic ("Bomb Disposal Robot -
QinetiQ") so the designation comes from the H1.

Product tree (verified live 2026-08-25):
/en/what-we-do/research-and-development/autonomous-systems/robotics/
  robotic-products/<slug>
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.qinetiq.com"

_BASE = ("https://www.qinetiq.com/en/what-we-do/research-and-development/"
         "autonomous-systems/robotics/robotic-products")

# Curated product pages. Controllers/kits/maintenance/disinfecting variants
# and the SeaScout UUV (no matching category) are deliberately excluded.
QINETIQ_PRODUCT_URLS: list[tuple[str, str]] = [
    (f"{_BASE}/talon-medium-sized-tactical-robot", "UGVs"),
    (f"{_BASE}/c-talon-submersible-security-robot", "UGVs"),
    (f"{_BASE}/dragon-runner-small-and-compact-robot", "UGVs"),
    (f"{_BASE}/maars", "UGVs"),
    (f"{_BASE}/spur-next-generation-backpackable-robot", "UGVs"),
]


def parse_qinetiq(url: str, html: str,
                  category_display: str = "UGVs") -> CatalogEntry | None:
    """Parse a qinetiq.com robotic-product page."""
    if not html:
        return None

    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
                  "", body, flags=re.S)

    name = ""
    for h in re.findall(r"<h1[^>]*>(.*?)</h1>", body, re.S | re.I):
        cand = re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<[^>]+>", "", h))).strip()
        if cand and len(cand) <= 100:
            name = re.sub(r"\s+", " ",
                          re.sub(r"[®™]", " ", cand)).strip()
            break
    if not name:
        return None

    desc = ""
    meta_m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"',
                       html, re.I)
    if meta_m:
        desc = html_lib.unescape(meta_m.group(1)).strip()
    if not desc:
        text = re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<[^>]+>", " ", body))).strip()
        i = text.find(name.split()[0])
        if i >= 0:
            seg = text[i:i + 400]
            stop = seg.find(". ")
            if stop > 80:
                desc = seg[:stop + 1].strip()
    if not desc:
        desc = f"QinetiQ robotic system: {name}"

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country="UK",
        manufacturer="QinetiQ",
        category=category_display,
        description=desc[:500],
        specs=[],
        sources=[SourceRef("QinetiQ", url)],
        fetched_at=now_iso(),
    )
