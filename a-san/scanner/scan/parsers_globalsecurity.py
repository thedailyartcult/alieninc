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


def parse_globalsecurity(url: str, html: str,
                         category_display: str = "") -> CatalogEntry | None:
    """Parse a /military/systems/<section>/<page>.htm content page."""
    if not html:
        return None

    h2_m = re.search(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)
    if not h2_m:
        return None
    name = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", h2_m.group(1)))).strip()
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
    specs: list[str] = []
    for p in paragraphs:
        pl = p.lower()
        if any(v in pl for v in _CAPABILITY_KWS):
            specs.append(p[:320])
        if not description and not pl.startswith(("©", "source:", "follow")) \
                and "cookie" not in pl and "advertise" not in pl:
            description = p[:600]
        if len(specs) >= 5 and description:
            break
    if not description and paragraphs:
        description = paragraphs[0][:600]
    # Pure-hub pages (no real content) yield nothing.
    if not description or len(paragraphs) < 1:
        return None

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
