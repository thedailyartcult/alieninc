"""Parser for milremrobotics.com — Milrem Robotics (Estonian UGV specialist).

robots.txt: User-agent:* allowed (only AI bots like Amazonbot/Applebot-Extended
are disallowed). No crawl-delay specified for our UA.
Content licence: no explicit © on product pages; corporate /terms-policies/
page exists. Fact-extraction with attribution — see POLICY.md.

UGV products (6): THeMIS family, HAVOC RCV, Vector RCV, MRCV, ARCOS, Type-X.
Specs are in clean repeating div blocks:
  <div class="flex justify-between border-b border-gray-500[ ...]">
    <p class="text-gray-500">Label</p><p class="text-black">Value</p>
  </div>
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "milremrobotics.com"

# The 6 UGV product page slugs (confirmed live, robots-allowed).
MILREM_PRODUCT_URLS = [
    "https://milremrobotics.com/themis-family/",
    "https://milremrobotics.com/havoc-rcv/",
    "https://milremrobotics.com/vector-rcv/",
    "https://milremrobotics.com/mrcv/",
    "https://milremrobotics.com/arcos/",
    "https://milremrobotics.com/type-x/",
]


def parse_milrem(url: str, html: str, category_display: str = "UGVs") -> CatalogEntry | None:
    """Parse a milremrobotics.com UGV product page."""
    if not html:
        return None

    # <title>THeMIS - Milrem</title>  or  <title>HAVOC RCV - Milrem</title>
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
    # Strip the " - Milrem" suffix
    title = re.sub(r"\s*[-–]\s*Milrem\s*$", "", title, flags=re.I).strip()
    if not title:
        return None

    # Spec blocks: <div class="flex justify-between border-b border-gray-500[ ...]">
    #   <p class="text-gray-500">Label</p><p class="text-...">Value</p>
    # </div>
    specs: list[str] = []
    block_re = re.compile(
        r'<div\s+class="flex\s+justify-between\s+border-b\s+border-gray-500[^"]*"[^>]*>'
        r'(.*?)</div>',
        re.S | re.I)
    for m in block_re.finditer(html):
        block = m.group(1)
        # Extract the two <p> children
        ps = re.findall(r"<p[^>]*>(.*?)</p>", block, re.S | re.I)
        if len(ps) >= 2:
            label = html_lib.unescape(re.sub(r"<[^>]+>", "", ps[0])).strip()
            value = html_lib.unescape(re.sub(r"<[^>]+>", "", ps[1])).strip()
            if label and value and label.lower() not in ("title", "data"):
                specs.append(f"{label}: {value}")

    # Description: find the first substantial <p> in the main content area.
    # Milrem pages have marketing prose; take the first 2-3 paragraphs that
    # aren't navigation/footer.
    body = ""
    # Try meta description first (often a clean summary)
    meta_m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if meta_m:
        body = html_lib.unescape(meta_m.group(1)).strip()
    if not body:
        # Fallback: first few <p> blocks with substantial text
        paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
        candidates = []
        for p in paras:
            text = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
            if len(text) > 60 and not text.startswith(("Milrem", "VAT", "All rights")):
                candidates.append(text)
            if len(candidates) >= 2:
                break
        body = " ".join(candidates)
    if not body:
        body = f"Milrem Robotics UGV: {title}"

    return CatalogEntry(
        designation=title,
        alt_names=[],
        country="Estonia",
        manufacturer="Milrem Robotics",
        category=category_display,
        description=body[:500],
        specs=specs[:25],
        sources=[SourceRef("Milrem Robotics", url)],
        fetched_at=now_iso(),
    )
