"""Parser for gdls.com — General Dynamics Land Systems (USA).

robots.txt: User-agent:* allow-all, Crawl-delay: 10 (enforced via
HttpFetcher.HOST_CRAWL_DELAY). Yoast WP sitemaps: /sitemap_index.xml.
Content licence: © General Dynamics — fact-extraction with attribution
(see POLICY.md): designation + description + exact source URL. Product pages
are WordPress prose (no spec tables); variant names become alt_names.

Product pages (flat slugs):
  /trx-fov/  TRACKED ROBOT 10-TON (TRX)          -> UGVs
  /mutt/     MULTI-UTILITY TACTICAL TRANSPORT    -> UGVs
  /stryker/  STRYKER family                      -> Armored vehicles
  /lav/      LAV family                          -> Armored vehicles
  /abrams/   ABRAMS MBT                          -> Armored vehicles
  /xm30/     XM30 Mechanized Infantry Combat     -> Armored vehicles

<title>TRACKED ROBOT 10-TON (TRX) - General Dynamics Land Systems</title>
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.gdls.com"

GDLS_PRODUCT_URLS: list[tuple[str, str]] = [
    ("https://www.gdls.com/trx-fov/", "UGVs"),
    ("https://www.gdls.com/mutt/", "UGVs"),
    ("https://www.gdls.com/stryker/", "Armored vehicles and equipment"),
    ("https://www.gdls.com/lav/", "Armored vehicles and equipment"),
    ("https://www.gdls.com/abrams/", "Armored vehicles and equipment"),
    ("https://www.gdls.com/xm30/", "Armored vehicles and equipment"),
]


def parse_gdls(url: str, html: str,
               category_display: str = "") -> CatalogEntry | None:
    """Parse a gdls.com product page."""
    if not html:
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "",
                                     title_m.group(1))).strip()
    name = re.split(r"\s*[-–|]\s*General Dynamics", title)[0].strip()
    if not name:
        return None

    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
                  "", body, flags=re.S)

    # Variant H2s that share the product's leading word or its parenthesized
    # acronym ("TRX BREACHER" under "TRACKED ROBOT 10-TON (TRX)").
    variants: list[str] = []
    leads = [name.split()[0]] if name.split() else []
    leads += re.findall(r"\(([A-Za-z0-9\-]{2,12})\)", name)
    if leads:
        lead_re = re.compile(
            rf"^({'|'.join(re.escape(l) for l in leads)})\b", re.I)
        for h in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S | re.I):
            cand = re.sub(r"\s+", " ", html_lib.unescape(
                re.sub(r"<[^>]+>", "", h))).strip()
            if cand != name and len(cand) < 60 and lead_re.match(cand):
                variants.append(cand)

    desc = ""
    meta_m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if meta_m:
        desc = html_lib.unescape(meta_m.group(1)).strip()
    if not desc:
        text = re.sub(r"\s+", " ",
                      html_lib.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
        for para in re.findall(r"[A-Z][^.]{80,400}\.", text):
            if not re.search(r"(cookie|privacy|copyright)", para, re.I):
                desc = para.strip()
                break
    if not desc:
        desc = f"General Dynamics Land Systems vehicle: {name}"
    if variants:
        desc = f"{desc} Variants: {', '.join(variants[:5])}."

    return CatalogEntry(
        designation=name,
        alt_names=variants[:8],
        country="USA",
        manufacturer="General Dynamics Land Systems",
        category=category_display or "Uncategorized",
        description=desc[:500],
        specs=[],
        sources=[SourceRef("General Dynamics Land Systems", url)],
        fetched_at=now_iso(),
    )
