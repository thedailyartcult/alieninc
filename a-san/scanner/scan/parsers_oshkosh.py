"""Parser for oshkoshdefense.com — Oshkosh Defense (USA tactical trucks).

robots.txt: User-agent:* allow-all, Crawl-delay: 10 (enforced via
HttpFetcher.HOST_CRAWL_DELAY). Yoast WP sitemaps: /sitemap_index.xml.
Content licence: © Oshkosh Defense — fact-extraction with attribution
(see POLICY.md): designation + description + exact source URL. Pages are
Elementor/WordPress prose with high-quality meta descriptions; no spec
tables in the served HTML.

Vehicle pages follow /vehicles/<class>/<slug>/:
  light-tactical-vehicles/jltv, l-atv        -> Automotive vehicles
  medium-tactical-vehicles/fmtv-a2, mtvr     -> Automotive vehicles
  heavy-tactical-vehicles/hemtt, het, ...    -> Automotive vehicles
  combat-vehicles/rcv                        -> UGVs (Robotic Combat Vehicle)
  combat-vehicles/integrated-weapons-system  -> Armored vehicles and equipment
  mine-resistant-ambush-protected-mrap       -> Armored vehicles and equipment

<title>HEMTT (Heavy Expanded Mobility Tactical Truck) | Oshkosh Defense</title>
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "oshkoshdefense.com"

_CATEGORY_BY_PATH = [
    ("combat-vehicles/rcv", "UGVs"),
    ("integrated-weapons-system", "Armored vehicles and equipment"),
    ("mine-resistant", "Armored vehicles and equipment"),
    ("light-tactical", "Automotive vehicles"),
    ("medium-tactical", "Automotive vehicles"),
    ("heavy-tactical", "Automotive vehicles"),
    ("aircraft-rescue", "Automotive vehicles"),
]


def categorize_oshkosh_url(url: str) -> str | None:
    """Category for a vehicle page URL, or None to skip.

    Only concrete vehicle pages are accepted: two-segment /vehicles/x/y/
    paths plus the single-segment MRAP and ARFF pages. Class hub pages
    (/vehicles/light-tactical-vehicles/ etc.) and the generic marketing
    pages under combat-vehicles/ yield no usable designation and are
    deliberately skipped."""
    path = urllib.parse.urlsplit(url).path.lower()
    m = re.match(r"^/vehicles/([^/]+)/(?!$)([^/]+)/?$", path)
    if not m:
        # explicit single-segment product pages worth keeping
        if re.match(r"^/vehicles/mine-resistant-ambush-protected-mrap/?$",
                    path) or \
                re.match(r"^/vehicles/aircraft-rescue-fire-fighting-arff/?$",
                         path):
            return "Armored vehicles and equipment" if "mrap" in path \
                else "Automotive vehicles"
        return None
    cls, slug = m.group(1), m.group(2)
    if cls == "combat-vehicles":
        return None  # marketing pages, no per-product designations yet
    for kw, cat in _CATEGORY_BY_PATH:
        if kw in path:
            return cat
    return None


def parse_oshkosh(url: str, html: str,
                  category_display: str = "") -> CatalogEntry | None:
    """Parse an oshkoshdefense.com vehicle page."""
    if not html:
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
    name = re.split(r"\s*\|\s*", title)[0].strip()
    # Drop the parenthetical expansion from the designation but keep it as an
    # alt name: "HEMTT (Heavy Expanded Mobility Tactical Truck)".
    alt_names: list[str] = []
    paren_m = re.match(r"^(.*?)\s*\((.+)\)\s*$", name)
    if paren_m:
        alt_names.append(paren_m.group(2).strip())
        name = paren_m.group(1).strip()
    if not name:
        return None

    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
                  "", body, flags=re.S)

    desc = ""
    meta_m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if meta_m:
        desc = html_lib.unescape(meta_m.group(1)).strip()
    if not desc:
        text = re.sub(r"\s+", " ",
                      html_lib.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
        for para in re.findall(r"[A-Z][^.]{80,400}\.", text):
            if not re.search(r"(cookie|privacy|copyright|subscribe)", para, re.I):
                desc = para.strip()
                break
    if not desc:
        desc = f"Oshkosh Defense vehicle: {name}"

    return CatalogEntry(
        designation=name,
        alt_names=alt_names[:4],
        country="USA",
        manufacturer="Oshkosh Defense",
        category=category_display or "Automotive vehicles",
        description=desc[:500],
        specs=[],
        sources=[SourceRef("Oshkosh Defense", url)],
        fetched_at=now_iso(),
    )
