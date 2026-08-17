"""Parser for en.wikipedia.org — military electronics lists and EW system pages.

robots.txt: User-agent:* allowed (only aggressive scrapers are rate-limited; the
API at /w/api.php is the sanctioned high-volume route). No crawl-delay for our
polite fetcher.
Content licence: Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0) —
this is the FIRST source in the A-SAN catalog whose content can be FREELY
REPUBLISHED on the website with attribution. Every entry carries the Wikipedia
source URL and a CC BY-SA 4.0 attribution notice.

Two page types parsed:
  1. List pages — "List of military electronics of the United States: A–G" and
     "M–Z". Each has 100+ wikitables with columns:
     Designation | Purpose/Description | Location/Used by | Manufacturer
  2. Infobox pages — individual EW system pages (AN/ALQ-99, AN/SLQ-32, Krasukha,
     etc.) with a structured infobox containing specs (Type, Place of origin,
     Manufacturer, Frequency Range, Operational range, Platform, etc.).
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "en.wikipedia.org"

# The two master list pages (A–G and M–Z).
WIKIPEDIA_LIST_URLS = [
    "https://en.wikipedia.org/wiki/List_of_military_electronics_of_the_United_States:_A%E2%80%93G",
    "https://en.wikipedia.org/wiki/List_of_military_electronics_of_the_United_States:_M%E2%80%93Z",
]


def _clean(text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace, remove CSS noise."""
    # Remove CSS style blocks that leak through (e.g. .mw-parser-output .vanchor...)
    text = re.sub(r"\.mw-parser-output[^}]*\}", "", text)
    text = re.sub(r"@media[^}]*\}", "", text)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    # Remove Wikipedia citation reference numbers like [8], [5], [12][13]
    text = re.sub(r"\[\d+(?:\]\[\d+)*\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_wikipedia_list(html: str, source_url: str) -> list[CatalogEntry]:
    """Parse a Wikipedia "List of military electronics" page.

    Extracts every row from every wikitable with the Designation/Purpose schema.
    Returns a list of CatalogEntry objects (category assigned by the row content).
    """
    if not html:
        return []
    entries: list[CatalogEntry] = []
    # Find all wikitables with the Designation + Purpose schema
    table_re = re.compile(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        re.S | re.I)
    for tbl_m in table_re.finditer(html):
        tbl = tbl_m.group(1)
        # Verify this is a Designation table (has the right headers)
        if "Designation" not in tbl or "Purpose" not in tbl:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I)
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            if len(cells) < 2:
                continue
            # Skip header rows (first cell is "Designation")
            first = _clean(cells[0])
            if first.lower() == "designation":
                continue
            designation = first
            purpose = _clean(cells[1]) if len(cells) > 1 else ""
            used_by = _clean(cells[2]) if len(cells) > 2 else ""
            manufacturer = _clean(cells[3]) if len(cells) > 3 else ""
            # Skip empty designations
            if not designation or len(designation) < 3:
                continue
            # Clean up CSS noise that leaks into the first cell
            designation = re.sub(r"\.mw-parser-output.*?\}", "", designation).strip()
            if not designation or len(designation) < 3:
                continue
            # Classify into A-SAN category
            category = _classify_wiki_entry(designation, purpose, used_by)
            # Build specs list from structured fields
            specs: list[str] = []
            if purpose:
                specs.append(f"Purpose: {purpose[:200]}")
            if used_by:
                specs.append(f"Platform: {used_by}")
            if manufacturer:
                specs.append(f"Manufacturer: {manufacturer}")
            # Description is the purpose field
            desc = purpose or f"US military electronic system: {designation}"
            entries.append(CatalogEntry(
                designation=designation,
                alt_names=[],
                country="USA",
                manufacturer=manufacturer,
                category=category,
                description=desc[:500],
                specs=specs[:10],
                sources=[SourceRef("Wikipedia (CC BY-SA 4.0)", source_url)],
                fetched_at=now_iso(),
            ))
    return entries


def parse_wikipedia_infobox(url: str, html: str, category_display: str = "") -> CatalogEntry | None:
    """Parse a Wikipedia individual EW system page with an infobox.

    Extracts the infobox spec table (Type, Place of origin, Manufacturer,
    Frequency Range, Operational range, Platform, etc.) + the lead paragraph.
    """
    if not html:
        return None

    # <title>AN/ALQ-99 - Wikipedia</title>
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = _clean(title_m.group(1))
    title = re.sub(r"\s*-\s*Wikipedia\s*$", "", title, flags=re.I).strip()
    if not title:
        return None

    # Infobox: <table class="infobox ...">...</table>
    infobox_m = re.search(
        r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>(.*?)</table>',
        html, re.S | re.I)
    specs: list[str] = []
    country = ""
    manufacturer = ""
    if infobox_m:
        ib = infobox_m.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", ib, re.S | re.I)
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            if len(cells) < 2:
                continue
            label = _clean(cells[0])
            value = _clean(cells[1])
            if not label or not value:
                continue
            # Skip section headers (colspan rows like "Service history", "Specifications")
            if len(cells) == 1 or "colspan" in row.lower():
                continue
            ll = label.lower().rstrip("s:").rstrip(":")
            # Map common infobox fields
            if ll in ("place of origin", "origin", "country"):
                if not country:
                    country = value
            elif ll in ("manufacturer", "manufacturer(s)", "designer", "designer(s)"):
                if not manufacturer:
                    manufacturer = value
            # Add all label:value pairs as specs
            specs.append(f"{label}: {value}")

    # Description: first <p> after the infobox (lead paragraph)
    body = ""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
    for p in paras:
        text = _clean(p)
        if len(text) > 60 and not text.lower().startswith(("wikipedia", "this article", "this is a")):
            body = text
            break
    if not body:
        body = f"Wikipedia article: {title}"

    # Category
    if not category_display or category_display == "Uncategorized":
        category_display = _classify_wiki_entry(title, body, "")

    return CatalogEntry(
        designation=title,
        alt_names=[],
        country=country,
        manufacturer=manufacturer,
        category=category_display,
        description=body[:500],
        specs=specs[:25],
        sources=[SourceRef("Wikipedia (CC BY-SA 4.0)", url)],
        fetched_at=now_iso(),
    )


def _classify_wiki_entry(designation: str, purpose: str, used_by: str) -> str:
    """Classify a Wikipedia military-electronics entry into an A-SAN category."""
    text = f"{designation} {purpose} {used_by}".lower()

    # EW assets — the primary target for this source
    ew_keywords = (
        "electronic warfare", "electronic countermeasure", "jammer", "jamming",
        "ecm", "eCCm", "sigint", "elint", "comint", "radar warning", "rwr",
        "countermeasure", "decoy", "chaff", "flare", "ircm", "dircm",
        "spectrum", "electromagnetic", "ew system", "electronic support",
        "radar", "sonar", "sensor", "surveillance", "warning receiver",
        "an/alq", "an/ale", "an/alr", "an/alt", "an/slr", "an/slq",
        "an/blq", "an/aaq-24", "an/aar", "krasukha", "khibiny", "murmansk",
        "pole-21", "r-330", "zhitel", "koral", "leer", "infauna",
        "filin", "scorpius", "compass call", "growler", "prowler",
    )
    if any(kw in text for kw in ew_keywords):
        return "EW assets"

    # Air-launched munitions
    if any(kw in text for kw in ("air-to-air", "air-to-surface", "air-launched",
                                  "aim-", "agm-", "gcb", "jdam", "amraam",
                                  "sidewinder", "guided bomb")):
        return "Air-launched munitions"

    # Rocket and missile weapons
    if any(kw in text for kw in ("missile", "rocket", "sam ", "air defense",
                                  "ballistic", "cruise", "atgm", "torpedo",
                                  "patriot", "thaad", "s-400")):
        return "Rocket and missile weapons"

    # Aircraft
    if any(kw in text for kw in ("aircraft", "helicopter", "fighter", "bomber",
                                  "transport ", "trainer", "reconnaissance aircraft",
                                  "awacs", "aew", "uav", "drone", "unmanned aerial")):
        return "Aircraft"

    # Naval vessels
    if any(kw in text for kw in ("ship", "vessel", "frigate", "destroyer",
                                  "submarine", "carrier", "corvette")):
        return "Naval vessels"

    # Default: EW assets (this source is EW-focused)
    return "EW assets"
