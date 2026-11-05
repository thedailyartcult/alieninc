"""Parser for militaryfactory.com aircraft pages.

Two page shapes are supported:

1. "Aircraft by Country" list pages — country index pages scraped by the
   operator. Each page lists aircraft operated by that country, one row per
   type:
     <a href="/aircraft/detail.php?aircraft_id=N" ...>
       <div class="rsContainerPlate">
         <div class="letterGroupContainer">rank</div>
         <img class="acImgFormatting" src="/aircraft/imgs/sml/xxx.jpg">
         <div class="rsYearFlag">flag <span class="textNormal textWhite">YYYY</span></div>
         <div class="rsACname">
           <span class="textLarge textBold textDkGray">NAME</span>
           <span class="textNormal textGray">DESCRIPTOR</span>
         </div>
       </div>
     </a>

   The `aircraft_id` is stable across countries, so it is the merge key: the
   same aircraft listed under several countries accumulates those operators.

2. Detail pages (/aircraft/detail.php?aircraft_id=N) — fetched live by the
   scanner now that the robots gate uses our UA. They carry collapsible spec
   panels (Propulsion, Performance, Structural, Armament, Operators) plus an
   intro paragraph; the parser extracts the labeled spec rows as specs.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

ENTRY_RE = re.compile(
    r'<a href="(/aircraft/detail\.php\?aircraft_id=(\d+))"[^>]*>(.*?)</a>',
    re.S)

NAME_RE = re.compile(r'class="textLarge textBold textDkGray">([^<]+)</span>')
DESC_RE = re.compile(r'class="textNormal textGray">([^<]+)</span>')
YEAR_RE = re.compile(r'class="textNormal textWhite">(\d{4})<')
IMG_RE = re.compile(r'class="acImgFormatting"[^>]*src="(/aircraft/imgs/[^"]+)"')

# Descriptors that mark an entry as civilian-only (no defense relevance).
CIVIL_ONLY = [
    "passenger airliner", "airliner", "business jet", "bizjet", "general aviation",
    "light sports", "sports plane", "crop", "agricultural", "commuter",
    "light sport", "glider", "ultralight", "air taxi", "flying car", "tourism",
    "recreational", "executive transport", "passenger aircraft", "narrow-body",
    "wide-body", "regional jet", "light-class passenger", "passenger jet",
    "regional passenger", "passenger flying boat",
]

# Descriptors that mark defense relevance even when the airframe is civil.
MILITARY_ROLE = [    "aerial refueling", "tanker", "early warning", "awacs", "reconnaissance",
    "surveillance", "maritime patrol", "anti-submarine", "asw", "electronic",
    "jamming", "sigint", "special operations", "military", "combat", "fighter",
    "bomber", "attack", "gunship", "strike", "trainer", "transport", "patrol",
    "interceptor", "rescue", "search and rescue", "sar", "evacuation",
    "observation", "liaison", "utility", "multirole", "multi-role", "strategic",
    "tactical", "stealth", "missile", "drone", "uav", "uas", "unmanned",
    "loitering", "helicopter", "rotorcraft", "demonstrator", "prototype",
    "testbed", "experimental", "research", "concept", "proposal", "project",
    "escort", "interdiction", "close air support", "cas", "maritime service",
    "anti-ship", "scout", "seaplane", "anti-submarine", "mine countermeasures",
    "aerial surveillance", "signals intelligence", "fire support",
]


def _extract_row(block: str, aircraft_id: int, url: str) -> dict | None:
    name_m = NAME_RE.search(block)
    desc_m = DESC_RE.search(block)
    year_m = YEAR_RE.search(block)
    img_m = IMG_RE.search(block)
    if not name_m:
        return None
    return {
        "aircraft_id": aircraft_id,
        "name": html_lib.unescape(name_m.group(1).strip()),
        "descriptor": html_lib.unescape(desc_m.group(1).strip()) if desc_m else "",
        "year": year_m.group(1) if year_m else "",
        "image": img_m.group(1) if img_m else "",
        "url": "https://www.militaryfactory.com" + url,
    }


# File-code -> operator country display name (from the scraped filename stem).
COUNTRY_NAMES = {
    "BRA": "Brazil", "CAN": "Canada", "CHI": "China", "FRA": "France",
    "IND": "India", "ISR": "Israel", "JPN": "Japan", "RUS": "Russia",
    "SOK": "South Korea", "SWE": "Sweden", "TUR": "Turkey", "UK": "United Kingdom",
    "UKR": "Ukraine", "US": "United States", "USSR": "Soviet Union",
}


def _country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code.upper(), code)


def parse_militaryfactory_country(html: str, country: str) -> list[dict]:
    """Parse one by-country page into raw rows (dedupe by aircraft_id is done
    by the caller so operators can be merged across pages)."""
    rows: dict[int, dict] = {}
    for m in ENTRY_RE.finditer(html or ""):
        row = _extract_row(m.group(3), int(m.group(2)), m.group(1))
        if row is None:
            continue
        # same aircraft_id: keep first-seen name/descriptor/year, append operator
        if row["aircraft_id"] in rows:
            rows[row["aircraft_id"]]["operators"].add(_country_name(country))
        else:
            row["operators"] = {_country_name(country)}
            rows[row["aircraft_id"]] = row
    return list(rows.values())


def _is_civilian(name: str, descriptor: str) -> bool:
    low = f"{name} {descriptor}".lower()
    if any(k in low for k in MILITARY_ROLE):
        return False
    return any(k in low for k in CIVIL_ONLY)


def classify_militaryfactory(name: str, descriptor: str) -> str:
    """Map a militaryfactory aircraft row onto a catalog category."""
    low = f"{name} {descriptor}".lower()
    if any(k in low for k in ("uav", "uas", "drone", "unmanned", "loitering")):
        return "UAVs"
    if any(k in low for k in ("hypersonic glide", "glide vehicle", "ballistic missile",
                              "missile", "cruise missile")):
        return "Rocket and missile weapons"
    return "Aircraft"


def build_entries(rows: list[dict]) -> list[CatalogEntry]:
    """Convert raw merged rows into catalog entries. Each row carries:
    aircraft_id, name, descriptor, year, image, url, operators (set)."""
    out: list[CatalogEntry] = []
    for r in rows:
        if _is_civilian(r["name"], r["descriptor"]):
            continue
        specs = []
        if r["year"]:
            specs.append(f"Year: {r['year']}")
        ops = sorted(r.get("operators") or set())
        if ops:
            specs.append("Operators: " + ", ".join(ops))
        description = r["descriptor"] or (
            f"Military and civilian aircraft profile of {r['name']} listed on "
            "MilitaryFactory.com.")
        entry = CatalogEntry(
            designation=r["name"],
            category=classify_militaryfactory(r["name"], r["descriptor"]),
            description=description,
            country=", ".join(ops),
            specs=specs[:20],
            sources=[SourceRef("MilitaryFactory.com", r["url"])],
            fetched_at=now_iso(),
        )
        out.append(entry)
    return out


# ---- detail pages (live-fetched by the scanner) ----

# A spec row inside a collapsible panel:
#   <div class="specContainerMain [specContainerShort] specBGcolor1">
#     <span class="textNormal textDkGray">LABEL</span><br />
#     <span class="textBold textLargest textDkGray">VALUE</span><br />
#     <span class="textNormal textDkGray">(UNITS)</span>
#   </div>
SPEC_ROW_RE = re.compile(
    r'<div class="specContainerMain[^"]*">.*?'
    r'<span class="textNormal textDkGray">([^<]+)</span>\s*<br\s*/?>'
    r'\s*<span class="textBold textLargest textDkGray">([^<]+)</span>',
    re.S)

# Free-text panels (Propulsion/Armament) and long-form content blocks:
#   <div class="specContainerMain specBGcolor1" ...><span ...>CONTENT</span></div>
PROSE_BLOCK_RE = re.compile(
    r'<div class="specContainerMain specBGcolor1"[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</div>',
    re.S)

# Intro/body paragraph: <div class="contentStripOuter stripBGcolor3"><span ...>...</span>
INTRO_BLOCK_RE = re.compile(
    r'<div class="contentStripOuter stripBGcolor3"[^>]*>\s*'
    r'<div class="contentStripInner"[^>]*>\s*'
    r'<span class="textLarge textDkGray">(.*?)</span>', re.S)

PANEL_HEADER_RE = re.compile(
    r'<button class="collapsible picTrans">\s*'
    r'<div class="titleContainer">\s*'
    r'<span class="textWhite textLarge">([^<]+)</span>', re.S)

SECTION_HEADER_RE = re.compile(r'<span class="textLarger textDkGray textBold">([^<]+)</span>')

# Mission Roles: <div class="roleContainers">ROLE</div> (text directly inside)
ROLE_CONTAINER_RE = re.compile(r'<div class="roleContainers">\s*([^<]+?)\s*</div>', re.S)

COMMON_SPEC_LABELS = {
    "crew", "length", "width", "height", "weight", "empty weight", "mto",
    "maximum takeoff", "propulsion", "engine", "maximum speed", "cruise speed",
    "service ceiling", "operational range", "rate-of-climb", "rate of climb",
    "wingspan", "wing area", "thrust-to-weight", "power", "armament",
    "number of hardpoints", "first flight", "introduction", "produced",
}


def _clean_text(s: str) -> str:
    s = html_lib.unescape(s)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_militaryfactory_detail(url: str, html: str) -> CatalogEntry | None:
    """Parse a militaryfactory.com aircraft detail page into a catalog entry.

    Merges the spec rows with the existing list-page data when a matching
    entry is already in the store (same designation). Returns None if the page
    does not look like an aircraft detail page."""
    if not html:
        return None
    # Name + descriptor + origin/year from the page header:
    #   <h1 class="textJumbo"><span class="textBold">NAME</span></h1>
    #   <h2 class="textLarge">DESCRIPTOR</h2>
    #   <h3 class="textLarger textBold">Country | Year</h3>
    h1 = re.search(r'<h1[^>]*>\s*<span[^>]*>([^<]+)</span>', html, re.S)
    h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.S)
    h3 = re.search(r'<h3[^>]*>([^<]+)</h3>', html, re.S)
    if not h1:
        return None
    name = _clean_text(h1.group(1))
    descriptor = _clean_text(h2.group(1)) if h2 else ""
    origin = _clean_text(h3.group(1)) if h3 else ""  # "Country | Year"

    specs: list[str] = []
    description_parts: list[str] = []

    # Collect spec rows (label/value/units) inside collapsible panels.
    for m in SPEC_ROW_RE.finditer(html):
        label = _clean_text(m.group(1))
        value = _clean_text(m.group(2))
        if not label or not value:
            continue
        if label.lower() in COMMON_SPEC_LABELS or re.search(r'\d', value):
            specs.append(f"{label}: {value}")

    # Mission Roles: the uppercase role tags (AIR-TO-AIR COMBAT, INTERCEPTION, ...).
    roles: list[str] = []
    seen_roles: set[str] = set()
    for m in ROLE_CONTAINER_RE.finditer(html):
        role = _clean_text(m.group(1))
        if not role or role in seen_roles:
            continue
        seen_roles.add(role)
        # roleContainers may wrap other divs; keep only uppercase role tokens
        if role.replace(" ", "").replace("-", "").replace("/", "").isalnum() and \
           any(c.isupper() for c in role):
            roles.append(role)

    # Long-form prose blocks: Propulsion/Armament/Operators summaries.
    for m in PROSE_BLOCK_RE.finditer(html):
        txt = _clean_text(m.group(1))
        if len(txt) < 40:
            continue
        desc = " ".join(txt.split())
        if desc not in description_parts:
            description_parts.append(desc)

    if not specs and not description_parts and not roles:
        return None

    # Description: prefer the descriptive prose (intro/armament), truncated.
    description = ""
    for part in description_parts:
        if any(k in part.lower() for k in ("introduction", "developed", "first flight",
                                           "entered service", "production", "series",
                                           "aircraft")):
            description = part
            break
    if not description and description_parts:
        description = description_parts[0]
    description = (description or descriptor or name)[:600]

    # Origin ("Country | Year") contributes a spec and country when present.
    specs.append(f"Type: {descriptor}") if descriptor else None
    country = ""
    if origin and " | " in origin:
        country, _, year = origin.partition(" | ")
        country = country.strip()
        if year.strip().isdigit():
            specs.append(f"Year: {year.strip()}")
    if roles:
        specs.append("Roles: " + ", ".join(roles))

    return CatalogEntry(
        designation=name,
        category=classify_militaryfactory(name, descriptor),
        description=description,
        country=country,
        specs=specs[:24],
        sources=[SourceRef("MilitaryFactory.com", url)],
        fetched_at=now_iso(),
    )
