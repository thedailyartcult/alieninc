"""Parser for helis.com — Helicopter History Site database (since 1997).

robots.txt (2026-08-26): User-agent:* allowed except image dirs; sitemap
index present (models not enumerated there). Model pages:
/database/model/<id>/ -> <h1>Manufacturer Model</h1>, a spec table
(Engine/Capacity/Length (m)/Height (m)/Rotor/Weight...), variant history
table (<model>, <year>, <note>). Public-domain claim by the operator;
fact extraction with attribution.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.helis.com"

# Keys we accept from the spec table (label normalization applied).
_SPEC_KEY_OK = re.compile(
    r"(engine|capacity|length|height|rotor|weight|speed|range|ceiling|"
    r"power|payload|crew|empty|max take|service ceiling|fuel)", re.I)


def is_helis_model_url(url: str) -> bool:
    return bool(re.match(r"https://www\.helis\.com/database/model/\d+/?$",
                         url, re.I))


def parse_helis_listing(html: str) -> list[str]:
    """Extract model URLs from any helis.com page."""
    links = re.findall(r'href="(/database/model/\d+/?)"', html or "", re.I)
    out: list[str] = []
    seen: set[str] = set()
    for l in links:
        u = "https://www.helis.com" + (l if l.endswith("/") else l + "/")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(
        re.sub(r"<[^>]+>", " ", text))).strip()


def parse_helis_model(url: str, html: str,
                      category_display: str = "") -> CatalogEntry | None:
    """Parse one helis.com model page."""
    if not html:
        return None
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    name = _clean(h1_m.group(1)) if h1_m else ""
    if not name or len(name) > 120:
        return None

    specs: list[str] = []
    desc = ""
    variants: list[str] = []

    for tbl in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I)
        for row in rows:
            cells = [_clean(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
            cells = [c for c in cells if c]
            if len(cells) == 2 and _SPEC_KEY_OK.search(cells[0]) \
                    and len(cells[1]) <= 120:
                specs.append(f"{cells[0]}: {cells[1]}")
            elif len(cells) >= 3 and re.match(r"^[A-Za-z0-9\- ]{2,40}$", cells[0]) \
                    and re.match(r"^(19|20)\d{2}", cells[1]):
                # variant row: <name>, <year>, <description>
                note = cells[2][:140]
                variants.append(f"{cells[0]} ({cells[1]}): {note}"
                                if note else f"{cells[0]} ({cells[1]})")

    # Description: intro paragraph near the top of the article.
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html,
                  flags=re.S | re.I)
    for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I):
        t = _clean(p)
        if len(t) > 100:
            desc = t[:600]
            break

    if variants:
        specs.extend(variants[:8])
    if not specs and not desc:
        return None

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country="",
        manufacturer="",
        category=category_display or "Aircraft",
        description=desc,
        specs=specs[:22],
        sources=[SourceRef("Helis.com Helicopter Database", url)],
        fetched_at=now_iso(),
    )
