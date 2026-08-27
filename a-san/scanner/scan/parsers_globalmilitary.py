"""Parser for globalmilitary.net — open military equipment database.

robots.txt (2026-08-26): explicitly welcomes AI/research crawlers with
attribution ("AI assistants and search engines are welcome to read, index and
cite this site with attribution and a link"). No Crawl-delay; sitemap at
/sitemap.xml -> sitemap-main.xml enumerates every page. Citation format:
"GlobalMilitary.net, <page title>, <URL>, accessed <date>".

Detail pages: /{aircraft,ships,vehicles,missiles,bombs,firearms}/<code>/
Structure: <h1>, meta block (Origin links to /countries/<iso3>/, Type,
Status, Introduced), key-figure cards (.n), a Technical Specifications
<table class="spec"> with td.l/td.v pairs, an Operators .oplist block of
country names, and a Description .prose section.
"""
from __future__ import annotations

import html as html_lib
import re

from .config import classify_article, CATEGORY_KEYS
from .models import CatalogEntry, SourceRef, now_iso

GM_HOST = "www.globalmilitary.net"
GM_SITEMAP = "https://www.globalmilitary.net/sitemap-main.xml"

_HOST = "www.globalmilitary.net"

# Category-listing prefixes we never treat as detail pages.
_LISTING_SEGMENTS = {
    "category", "compare", "country", "in-service", "events", "ranking",
}

# URL section -> catalog category.
_GM_CATEGORY_BY_PATH = [
    ("/aircraft/category/uav/", "UAVs"),
    ("/aircraft/", "Aircraft"),
    ("/ships/", "Naval vessels"),
    ("/vehicles/", "Armored vehicles and equipment"),
    ("/missiles/category/aam/", "Air-launched munitions"),
    ("/missiles/category/asm/", "Air-launched munitions"),
    ("/missiles/", "Rocket and missile weapons"),
    ("/bombs/", "Air-launched munitions"),
    ("/firearms/", "Small arms"),
]


def gm_category_for(url: str) -> str | None:
    """Catalog category for a GM detail URL, or None to skip."""
    low = url.lower()
    for prefix, cat in _GM_CATEGORY_BY_PATH:
        if prefix in low:
            return cat
    return None


def is_gm_detail(url: str) -> bool:
    """True when the URL is an equipment detail page worth crawling."""
    m = re.match(r"https://www\.globalmilitary\.net/"
                 r"(aircraft|ships|vehicles|missiles|bombs|firearms)/([^/?#]+)/?$",
                 url, re.I)
    if not m:
        return False
    return m.group(2).lower() not in _LISTING_SEGMENTS


def parse_globalmilitary_listing(html: str, base_url: str = "") -> list[str]:
    """Extract detail URLs from a category listing page."""
    if not html:
        return []
    out = []
    for m in re.finditer(r'href="(/(?:aircraft|ships|vehicles|missiles|bombs'
                         r"|firearms)/[a-z0-9-]+/)\"", html, re.I):
        out.append("https://www.globalmilitary.net" + m.group(1))
    seen: set[str] = set()
    deduped = []
    for u in out:
        u = u.rstrip("/") + "/"
        if u not in seen and is_gm_detail(u):
            seen.add(u)
            deduped.append(u)
    return deduped


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(
        re.sub(r"<[^>]+>", " ", text))).strip()


def parse_globalmilitary(url: str, html: str,
                         category_display: str = "") -> CatalogEntry | None:
    """Parse one globalmilitary.net equipment detail page."""
    if not html:
        return None

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    name = _clean(h1_m.group(1)) if h1_m else ""
    # 'Missile 2K11 (SA-4 Ganef)' / 'Ship Abhay class' — drop the leading
    # equipment-kind word when present.
    name = re.sub(r"^(Missile|Aircraft|Ship|Vehicle|Tank|Helicopter|Drone|"
                  r"Firearm|Bomb)\s+", "", name, flags=re.I).strip()
    if not name or len(name) > 160:
        return None

    specs: list[str] = []

    # Meta block: Origin / Type / Status / Introduced rows.
    origin = ""
    for hs in re.finditer(r'<div class="hs">\s*<span class="k">([^<]+)</span>'
                          r'\s*<span class="v[^"]*">(.*?)(?=<div class="hs">|'
                          r"</aside>)", html, re.S | re.I):
        label = _clean(hs.group(1))
        val_html = hs.group(2)
        if label == "Origin":
            origins = [_clean(a) for a in re.findall(
                r"<a[^>]*href=\"/countries/[a-z]{3}/\"[^>]*>\s*([^<]+?)\s*</a>",
                val_html)]
            if not origins:
                origins = [t for t in (_clean(x) for x in re.findall(
                    r"<span[^>]*>(.*?)</span>", val_html, re.S)) if t]
            seen_o: list[str] = []
            for o in origins:
                if o.lower() in {x.lower() for x in seen_o} \
                        or o.lower().startswith("ex-"):
                    continue
                seen_o.append(o)
            origin = ", ".join(seen_o[:4])
        elif label == "Type":
            specs.append(f"Type: {_clean(val_html)}")
        elif label == "Status":
            specs.append(f"Status: {_clean(val_html)}")
        elif label == "Introduced":
            specs.append(f"Introduced: {_clean(val_html)}")

    # Key figures: <span class="k">Range</span><div class="n">50<small>km</small>
    for m in re.finditer(
            r'<span class="k">([A-Za-z ./-]{2,30}?)</span>\s*'
            r'<div class="n">(.*?)</div>', html, re.S | re.I):
        label = _clean(m.group(1))
        val = _clean(m.group(2))
        if label and val and len(val) <= 60:
            specs.append(f"{label}: {val}")

    # Technical Specifications table.
    tbl_m = re.search(r'<table class="spec">(.*?)</table>', html, re.S | re.I)
    if tbl_m:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl_m.group(1), re.S | re.I):
            cells = re.findall(r'<td class="[lv]"[^>]*>(.*?)</td>', row, re.S)
            if len(cells) == 2:
                k = _clean(cells[0])
                v = _clean(re.sub(r"<small>.*?</small>", "", cells[1],
                                  flags=re.S | re.I))
                if k and v:
                    specs.append(f"{k}: {v}")

    # Operators list (operator-nation semantics for the country field).
    operators = ""
    op_m = re.search(r'class="oplist[^"]*">(.*?)</div>', html, re.S | re.I)
    if op_m:
        ops = [t for t in (
            _clean(x) for x in re.findall(r"<span>(.*?)</span>",
                                          op_m.group(1), re.S | re.I)) if t]
        ops = [re.sub(r"^[\U0001F1E6-\U0001F1FF\u200d\ufe0f\W]+", "", o).strip()
               for o in ops]          # strip flag emoji + punctuation
        ops = [o for o in ops if o]
        deduped: list[str] = []
        for o in ops:
            if o.lower() not in {x.lower() for x in deduped}:
                deduped.append(o)
        operators = ", ".join(deduped)[:150]

    # Description: first prose paragraph.
    desc = ""
    prose_m = re.search(r'<div class="prose">\s*(?:<p[^>]*>)?(.*?)(?:</p>|</div>)',
                        html, re.S | re.I)
    if prose_m:
        desc = _clean(prose_m.group(1))[:600]
    if not desc:
        lede_m = re.search(r'class="lede-?text?"?[^>]*>(.*?)</', html, re.S | re.I)
        if lede_m:
            desc = _clean(lede_m.group(1))[:600]
    if not desc:
        return None

    if origin and f"origin: {origin.lower()}" not in " ".join(specs).lower():
        specs.insert(0, f"Origin: {origin}")

    if not category_display or category_display == "Uncategorized":
        category_display = gm_category_for(url) or ""
    if not category_display:
        key = classify_article(f"{name} {desc} {' '.join(specs)}")
        category_display = CATEGORY_KEYS[key] if key else ""

    country = operators or origin
    return CatalogEntry(
        designation=name,
        alt_names=[],
        country=country[:120],
        manufacturer="",
        category=category_display,
        description=desc,
        specs=specs[:25],
        sources=[SourceRef("GlobalMilitary.net", url)],
        fetched_at=now_iso(),
    )
