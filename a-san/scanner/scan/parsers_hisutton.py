"""Parser for hisutton.com — H I Sutton's "Covert Shores" naval analysis site.

robots.txt: absent (GitHub Pages 404) — no restrictions for any agent.
Flat article layout: <h1> system name, prose + spec tables covering
submarines, midget submarines, SDVs, UUVs and surface craft. © H I Sutton —
fact extraction with attribution (short description + facts + source URL).
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.hisutton.com"

_CAPABILITY_KWS = (" can ", " equipped ", " fitted ", " armed with ", " powered by ",
                   " displaced ", " displacement ", " range of ", " speed of ",
                   " crew of ", " torpedo", " launched")

# Conservative numeric fact patterns for table-less naval analysis prose.
# Each: (label, value_group_regex) where group 1 = number, group 2 = unit.
_FACT_RES = [
    ("Displacement",
     r"[Dd]isplacement[^.;]{0,30}?\b(\d{1,3}(?:[,.]\d+){0,2})\s*((?:long\s+)?(?:tons?|tonnes?))\b"),
    ("Length",
     r"\blength\b[^.;]{0,20}?\b(\d{1,3}(?:[,.]\d+)?)\s*(m|meters?|metres?|ft|feet)\b"),
    ("Beam",
     r"\bbeam\b[^.;]{0,20}?\b(\d{1,2}(?:[,.]\d+)?)\s*(m|meters?|metres?|ft|feet)\b"),
    ("Draft",
     r"\bdraft\b[^.;]{0,20}?\b(\d{1,2}(?:[,.]\d+)?)\s*(m|meters?|metres?|ft|feet)\b"),
    ("Speed",
     r"\bspeeds?\b[^.;]{0,25}?\b(\d{1,3}(?:\.\d+)?)\s*(knots?)\b"),
    ("Range",
     r"\brange\b[^.;]{0,25}?\b(\d{1,3}(?:[,.]\d+){0,2})\s*(nm|nautical miles|km|kilometers?|mi|miles)\b"),
    ("Crew",
     r"\bcrew\b(?:\s+of)?[^.;]{0,12}\b(\d{1,4})((?:\s*[+-]\s*\d{1,3})?)\b"),
]


def _prose_facts(text: str) -> list[str]:
    """Extract clean 'Key: value' facts from naval-analysis prose."""
    out: list[str] = []
    seen: set[str] = set()
    for key, pat in _FACT_RES:
        m = re.search(pat, text)
        if not m:
            continue
        num, unit = m.group(1).strip(), m.group(2).strip()
        if not num:
            continue
        pair = f"{key}: {num} {unit}".replace("  ", " ").strip()
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def parse_hisutton_article(url: str, html: str) -> CatalogEntry | None:
    """Parse a hisutton.com/<Article>.html page."""
    if not html:
        return None

    t_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    name = ""
    if h1_m:
        name = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1)))).strip()
    if not name and t_m:
        name = re.sub(r"\s+", " ", html_lib.unescape(t_m.group(1))).strip()
        name = re.sub(r"\s*\|\s*Covert Shores\s*$", "", name, flags=re.I).strip()
    if not name or len(name) > 200:
        return None

    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "",
                  html, flags=re.S | re.I)
    # Spec tables first (Property/Value rows), then prose paragraphs.
    specs: list[str] = []
    for table in re.findall(r"<table[^>]*>(.*?)</table>", body, re.S | re.I):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [
                re.sub(r"\s+", " ",
                       html_lib.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            ]
            if len(cells) >= 2 and cells[0] and cells[1]:
                specs.append(f"{cells[0]}: {cells[1]}")

    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I)]
    paragraphs = [re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
                  for p in paragraphs]
    paragraphs = [p for p in paragraphs
                  if len(p) > 60 and not p.startswith(("<time", "http", "@"))]

    description = ""
    for p in paragraphs:
        if not description:
            description = p[:600]
        break
    if not description and paragraphs:
        description = paragraphs[0][:600]
    if not description:
        return None

    # Specs: table rows when present; prose facts fill in otherwise.
    if len(specs) < 4:
        facts = _prose_facts(html_lib.unescape(re.sub(r"<[^>]+>", " ", body)))
        specs.extend(f for f in facts if f not in specs)

    return CatalogEntry(
        designation=name,
        category="Naval vessels",
        description=description,
        specs=specs[:20],
        sources=[SourceRef("Covert Shores (H I Sutton)", url)],
        fetched_at=now_iso(),
    )
