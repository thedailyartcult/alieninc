"""Parser for globalsecurity.org — GlobalSecurity.org military systems library.

robots.txt (2026-07-08): `User-agent:*` allowed except /phpadsnew/ and the
webinator search CGI. Cloudflare-style Content-Signals: search=yes,
ai-input=no, ai-train=no, use=reference — fact extraction with attribution is
permitted; raw text must NOT be used for AI training/fine-tuning. No
Crawl-delay for generic agents; the scanner's default politeness applies.

Tree: /military/systems/{munitions,aircraft,ground,...}/<page>.htm. Pages are
old-school HTML: <h2> carries the system name; specs are free-text paragraphs
under a "Specifications" anchor plus fact tables. Discovery recurses only into
index/hub pages (see cmd_discover_more) so leaves are enqueued without fetch.
© GlobalSecurity.org — fact extraction with attribution.
"""
from __future__ import annotations

import html as html_lib
import re

from .config import classify_article, CATEGORY_KEYS
from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.globalsecurity.org"

_CAPABILITY_KWS = (" can ", " features ", " equipped ", " fitted ", " powered by ",
                   " armed with ", " has a ", " carries ", " range of ", " in service",
                   " entered service", " caliber", " warhead", " launched")


def _gs_name(html: str) -> str:
    """System name: h2, else first meaningful h3/h1 (GS templates vary)."""
    generic = ("military", "systems", "specifications", "intelligence",
               "world", "policy", "about", "menu")
    for tag in ("h2", "h3", "h1"):
        for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.S | re.I):
            t = re.sub(r"\s+", " ",
                       html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
            if t and len(t) <= 160 and t.lower() not in generic:
                return t
    return ""


def _gs_spec_tables(body: str) -> list[str]:
    """'Specifications' fact tables: <th colspan=N>Specifications</th> then
    <tr><td>Label:</td><td [colspan=..]>value</td></tr>. Unit-suffix-only
    values ('pounds', 'inches') are folded into their label instead."""
    specs: list[str] = []
    for tbl_m in re.finditer(r"<table[^>]*>(.*?)</table>", body, re.S | re.I):
        tbl = tbl_m.group(1)
        if not re.search(r"<th[^>]*>\s*Specifications?\s*</th>", tbl, re.I):
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            texts = [
                re.sub(r"\s+", " ", html_lib.unescape(
                    re.sub(r"<[^>]+>", " ", c)).replace("&nbsp;", " ")).strip()
                for c in cells
            ]
            texts = [t for t in texts if t]
            if len(texts) < 2 or re.fullmatch(r"specifications?", texts[0], re.I):
                continue
            k = texts[0].rstrip(":")
            v = " ".join(texts[1:])
            # mk77-style unit stubs: value is just a unit -> keep as 'Weight: pounds'
            if v.lower() in ("pounds", "inches", "feet", "kg", "mm", "lbs"):
                specs.append(f"{k}: {v}")
            elif k and v and len(k) < 50:
                specs.append(f"{k}: {v}")
    return specs


def parse_globalsecurity(url: str, html: str,
                         category_display: str = "") -> CatalogEntry | None:
    """Parse a /military/systems/<section>/<page>.htm content page."""
    if not html:
        return None

    name = _gs_name(html)
    if not name or len(name) > 160:
        return None

    # Content paragraphs: strip scripts/styles first, then take <p> text.
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "",
                  html, flags=re.S | re.I)
    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I)]
    paragraphs = [re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
                  for p in paragraphs]
    paragraphs = [p for p in paragraphs if p and "freestar" not in p
                  and "@media" not in p and len(p) > 40]

    description = ""
    for p in paragraphs:
        pl = p.lower()
        if not description and not pl.startswith(("©", "source:", "follow")) \
                and "cookie" not in pl and "advertise" not in pl:
            description = p[:600]
        if description:
            break
    if not description and paragraphs:
        description = paragraphs[0][:600]
    # Pure-hub pages (no real content) yield nothing.
    if not description or len(paragraphs) < 1:
        return None

    # Specs: real fact tables only — prose sentences stay in the description.
    specs = _gs_spec_tables(body)

    text = f"{name} {description} {' '.join(specs)}".lower()
    if not category_display or category_display == "Uncategorized":
        key = classify_article(text)
        category_display = CATEGORY_KEYS[key] if key else ""
    if not category_display:
        # Section-path fallback: munitions -> missiles bucket.
        if "/munitions/" in url:
            category_display = "Rocket and missile weapons"
        elif "/aircraft/" in url:
            category_display = "Aircraft"
        elif "/ground/" in url:
            category_display = "Armored vehicles and equipment"
        else:
            return None

    return CatalogEntry(
        designation=name,
        category=category_display,
        description=description,
        specs=specs[:20],
        sources=[SourceRef("GlobalSecurity.org", url)],
        fetched_at=now_iso(),
    )
