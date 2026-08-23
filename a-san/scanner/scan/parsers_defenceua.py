"""Parser for en.defence-ua.com — Defense Express (English edition).

Ukrainian defence-analytics outlet; weapon_and_tech articles carry structured
specification tables (e.g. 2S22 Bohdana, Mace/Bulava UAS fact sheets).

robots.txt: User-agent:* allowed except /counter/, /search/, /pure/, query
strings (/*?*) and *.php paths. Sitemap index:
https://defence-ua.com/sitemap/sitemap.xml (monthly post-YYYY-MM.xml files).
Detail URLs carry no query string, so they are robots-clean.

Licence: (c) Defence Express, all rights reserved — fact-extraction only with
attribution (same policy as Army Recognition): factual data + spec tables +
short description + exact source URL. See POLICY.md.
"""
from __future__ import annotations

import html as html_lib
import re

from .config import classify_article, CATEGORY_KEYS
from .models import CatalogEntry, SourceRef, now_iso

_HOST = "en.defence-ua.com"


def parse_defenceua_article_listing(html: str) -> list[str]:
    """Extract article URLs from a sitemap or section listing page."""
    if not html:
        return []
    seen: dict[str, None] = {}
    for m in re.finditer(
            r'href="(https?://en\.defence-ua\.com/weapon_and_tech/[^"#?]+\.html)"',
            html):
        seen.setdefault(m.group(1), None)
    return list(seen)


def parse_defenceua_article(url: str, html: str,
                            category_display: str = "") -> CatalogEntry | None:
    """Parse an en.defence-ua.com/weapon_and_tech/<slug>-<id>.html article."""
    if not html:
        return None

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if not h1_m:
        t_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if not t_m:
            return None
        title_raw = t_m.group(1)
    else:
        title_raw = h1_m.group(1)
    designation = html_lib.unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()
    designation = re.sub(r"\s+", " ", designation)
    designation = re.sub(r"\s*\|\s*Defense Express\s*$", "", designation, flags=re.I).strip()
    # News-style titles often lead with a spec-sheet phrase; strip it so the
    # entry reads like a system name, e.g. "Upgraded 2S22 Bohdana Howitzer...".
    designation = re.sub(
        r"^(?:manufacturer\s+)?(?:reveals?\s+|shows?\s+)?"
        r"(?:full\s+)?specifications\s+of\s+|^(?:specs?|characteristics)\s+(?:of\s+)?",
        "", designation, flags=re.I).strip()
    if not designation:
        return None

    # Spec tables: <table><tr><td>Label</td><td>Value</td></tr>...</table>
    # Skip header rows (empty value cell) and merged cells.
    specs: list[str] = []
    for table in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [
                re.sub(r"\s+", " ",
                       html_lib.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            ]
            if len(cells) >= 2 and cells[0] and cells[1]:
                specs.append(f"{cells[0]}: {cells[1]}")

    # Description: first substantive paragraphs.
    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)]
    description = ""
    for p in paragraphs:
        pl = p.lower()
        if len(p) > 60 and not pl.startswith(("©", "source:", "subscribe", "follow")) \
                and "cookie" not in pl and "defence express ukr.defense.news" not in pl:
            description = p[:600]
            break
    if not description and paragraphs:
        description = next((p for p in paragraphs if p), "")[:600]

    body_text = f"{designation} {description} {' '.join(specs)}".lower()
    if not category_display or category_display == "Uncategorized":
        key = classify_article(body_text)
        category_display = CATEGORY_KEYS[key] if key else "Uncategorized"

    return CatalogEntry(
        designation=designation,
        category=category_display,
        description=description or f"Defense Express coverage: {designation}.",
        specs=specs[:24],
        sources=[SourceRef("Defense Express", url)],
        fetched_at=now_iso(),
    )
