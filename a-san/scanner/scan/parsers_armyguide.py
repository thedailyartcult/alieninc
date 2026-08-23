"""Parser for army-guide.com — Army Guide land-forces equipment database.

robots.txt: EMPTY (no restrictions for any agent; query-string listing URLs are
therefore robots-clean). Catalog: /eng/products.php (paginated ~65 pages) →
detail pages /eng/productNNNN.html. Each detail page carries two metadata tables
(Designation / Manufacturer / Product type / Name) and Property-Value spec
tables. © Army Guide — fact extraction with attribution.
"""
from __future__ import annotations

import html as html_lib
import re

from .config import CATEGORY_KEYS
from .models import CatalogEntry, SourceRef, now_iso

_HOST = "army-guide.com"

_PRODUCT_URL_RE = re.compile(
    r'href="((?:https?://(?:www\.)?army-guide\.com)?(?:/eng/)?(product\d+\.html))"', re.I)

# Product-type -> canonical category key
_TYPE_MAP = {
    "armoured vehicle": "armored-vehicles-and-equipment",
    "armored vehicle": "armored-vehicles-and-equipment",
    "tank": "armored-vehicles-and-equipment",
    "artillery": "rocket-and-missile-weapons",
    "missile": "rocket-and-missile-weapons",
    "rocket": "rocket-and-missile-weapons",
    "mortar": "rocket-and-missile-weapons",
    "small arm": "small-arms",
    "truck": "automotive-vehicles",
    "vehicle": "automotive-vehicles",
}


def parse_armyguide_listing(html: str) -> list[str]:
    """Extract product detail URLs from a products.php listing page."""
    if not html:
        return []
    seen: dict[str, None] = {}
    for m in _PRODUCT_URL_RE.finditer(html):
        url = m.group(1)
        if not url.startswith("http"):
            url = f"https://army-guide.com/eng/{m.group(2)}"
        seen.setdefault(url, None)
    return list(seen)


def parse_armyguide_product(url: str, html: str) -> CatalogEntry | None:
    """Parse an /eng/productNNNN.html equipment page."""
    if not html:
        return None

    meta: dict[str, str] = {}
    specs: list[str] = []
    in_specs = False
    for table in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        for row in rows:
            cells = [
                re.sub(r"\s+", " ",
                       html_lib.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            ]
            cells = [c for c in cells if c]
            if not cells:
                continue
            label = cells[0].rstrip(":")
            ll = label.lower()
            if len(cells) >= 2 and ll in ("designation", "manufacturer", "product type", "name"):
                meta[ll] = cells[1][:200]
                in_specs = False
            elif cells[0].lower().startswith("specification"):
                in_specs = True
            elif in_specs and len(cells) >= 2 and cells[0].lower() != "property":
                specs.append(f"{cells[0]}: {cells[1]}")

    designation = meta.get("designation", "")
    if not designation:
        t_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if not t_m:
            return None
        return None  # title is generic ("Army Guide") — no reliable name, skip.
    ptype = meta.get("product type", "")
    sysname = meta.get("name", "")

    cat_key = None
    for kw, key in _TYPE_MAP.items():
        if kw in ptype.lower():
            cat_key = key
            break
    category_display = CATEGORY_KEYS.get(cat_key, "") if cat_key else ""

    description = f"{ptype}: {sysname}." if ptype or sysname else ""
    if meta.get("manufacturer"):
        description += f" Listed by Army Guide."

    return CatalogEntry(
        designation=designation,
        category=category_display or "",
        country="",
        manufacturer=meta.get("manufacturer", ""),
        description=description.strip()[:600],
        specs=specs[:24],
        sources=[SourceRef("Army Guide", url)],
        fetched_at=now_iso(),
    )
