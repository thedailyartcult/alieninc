"""Parser for elbitsystems.com — Elbit Systems land-systems product pages.

robots.txt (verified live 2026-08-25): User-agent:* with only standard Drupal
boilerplate Disallows (/admin/, /user/, /core/...); /land/ is fully allowed;
no Crawl-delay. Content licence: © Elbit Systems — fact-extraction with
attribution (see POLICY.md §2): designation + factual specs + short
description + exact source URL, never wholesale prose.

Catalog enumeration: https://www.elbitsystems.com/sitemap.xml (Drupal
simple_sitemap module), filter <loc> URLs under /land/. Leaf products are
3+ path segments deep; section hubs (2 segments) are skipped by the parser's
spec check rather than the URL shape.

Page structure (verified 2026-08-25 on COMBATGUARD):
  - specs live in Drupal field--name-field-teaser divs as "- Key: value<br />"
  - designation in og:title / <title> ("COMBATGUARD Armored Fighting Vehicle AFV")
  - description in meta name="description"

Category routing is done at enqueue time from the URL path (see
cli.cmd_discover_round6); this parser trusts row["category"].
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "elbitsystems.com"


def elbit_category_for(url_path: str) -> str:
    """Map a /land/<section>/... path to an A-SAN category display name."""
    seg = url_path.split("/land/", 1)[-1].split("/")
    head = seg[0] if seg else ""
    sub = "/".join(seg[:2])
    if head == "combat-vehicle-systems" or head == "bridges":
        return "Armored vehicles and equipment"
    if head == "weapons-systems-and-munitions":
        return "Rocket and missile weapons"
    if head == "ammunition":
        return "Rocket and missile weapons"
    if head == "land-ew-sigint" or head == "land-c4isr":
        return "EW assets"
    if sub.startswith("infantry/ammunition"):
        return "Rocket and missile weapons"
    if head == "infantry":
        return "Small arms"
    return ""


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip(" -–—\t")


def parse_elbit(url: str, html: str,
                category_display: str = "") -> CatalogEntry | None:
    """Parse an elbitsystems.com /land/ product page."""
    if not html or "elbitsystems.com" not in url or "/land/" not in url:
        return None

    # --- designation ---
    name = ""
    m = re.search(r'property="og:title"\s+content="([^"]+)"', html, re.I) \
        or re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        name = _clean(m.group(1))
        # Titles carry SEO descriptors ("COMBATGUARD Armored Fighting Vehicle
        # AFV"); keep them — they disambiguate — but cap length.
        name = re.sub(r"\s*\|\s*Elbit Systems\s*$", "", name, flags=re.I)
    if not name or len(name) > 120:
        return None

    # --- specs: field--name-field-teaser blocks ("- Key: value<br />" lists) ---
    specs: list[str] = []
    for block in re.findall(
            r'field--name-field-teaser.*?>(.*?)</div>', html, re.S):
        for line in re.split(r"<br\s*/?>|\n", block):
            line = _clean(line)
            if line and len(line) <= 160 and ":" in line[:60] \
                    and not line.lower().startswith(("http", "www.")):
                specs.append(line.lstrip("-–— ").strip())

    # --- description ---
    desc = ""
    m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if m:
        desc = html_lib.unescape(m.group(1)).strip()

    # Hub pages (e.g. /land/combat-vehicle-systems/) have no teaser specs and
    # generic descriptions — skip them so only real products enter the store.
    if not specs:
        return None

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country="Israel",
        manufacturer="Elbit Systems",
        category=category_display,
        description=desc[:500],
        specs=specs,
        sources=[SourceRef("Elbit Systems product page", url)],
        fetched_at=now_iso(),
    )
