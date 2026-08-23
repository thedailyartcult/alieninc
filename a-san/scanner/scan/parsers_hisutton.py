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
        pl = p.lower()
        if any(v in pl for v in _CAPABILITY_KWS) and len(specs) < 8:
            specs.append(p[:320])
        if not description:
            description = p[:600]
        if description and len(specs) >= 6:
            break
    if not description and paragraphs:
        description = paragraphs[0][:600]
    if not description:
        return None

    return CatalogEntry(
        designation=name,
        category="Naval vessels",
        description=description,
        specs=specs[:20],
        sources=[SourceRef("Covert Shores (H I Sutton)", url)],
        fetched_at=now_iso(),
    )
