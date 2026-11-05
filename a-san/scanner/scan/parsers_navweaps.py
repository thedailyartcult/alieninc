"""Parser for navweaps.com — Tony DiGiulian's Naval Weapons reference.

robots.txt: fully allow-all ("#Robots.txt file allows all bots access to all
files", User-agent: * Allow: /). No crawl-delay.
Content licence: © Tony DiGiulian, all rights reserved — fact-extraction with
attribution (see POLICY.md): designation + spec table facts + short description
+ exact source URL; never wholesale prose.

SCOPE: only the WM* (naval missiles) sections are crawled. WN* (guns) and
WT* (torpedoes) have no matching catalog category and are deliberately skipped.

Detail page structure (e.g. /Weapons/WMUS_Tomahawk.php):
  <title>Tomahawk - Naval Missiles of the United States of America - NavWeaps</title>
  <h1>Tomahawk BGM-109</h1>
  <h2>Description</h2> ... prose <p>s ...
  <h2>Characteristics</h2>
  <table class="prettytable"><tr><th>Label</th><td>Value</td></tr>...</table>

Index pages (/Weapons/WMUS_Main.php etc.) list detail links as
<a href="WMUS_Tomahawk.php">...</a>.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.navweaps.com"

# Country extraction from the <title>: "Naval Missiles of X - NavWeaps"
_COUNTRY_MAP = {
    "united states": "USA",
    "russia/ussr": "Russia/USSR",
    "russia": "Russia",
    "ussr": "Russia/USSR",
    "great britain": "UK",
    "britain": "UK",
    "france": "France",
    "germany": "Germany",
    "italy": "Italy",
    "japan": "Japan",
    "china/prc": "China",
    "china": "China",
    "sweden": "Sweden",
    "norway": "Norway",
    "argentina": "Argentina",
    "australia": "Australia",
    "brazil": "Brazil",
    "chile": "Chile",
    "finland": "Finland",
    "india": "India",
    "netherlands": "Netherlands",
    "spain": "Spain",
}

_DETAIL_RE = re.compile(r'href="(WM[A-Z]{2,4}_[^"/]+?\.php)"', re.I)
_EXCLUDE_RE = re.compile(r"_Main\.php$|index", re.I)


def parse_navweaps_missile_links(html: str) -> list[str]:
    """Extract missile detail page hrefs from a WM*_Main.php index page."""
    out: list[str] = []
    seen: set[str] = set()
    if not html:
        return out
    for m in _DETAIL_RE.finditer(html):
        href = m.group(1)
        if _EXCLUDE_RE.search(href) or href in seen:
            continue
        seen.add(href)
        out.append(f"https://{_HOST}/Weapons/{href}")
    return out


def is_navweaps_missile_detail(url: str) -> bool:
    """True for WMxxx_<name>.php detail pages (not _Main.php index pages)."""
    path = url.rsplit("/", 1)[-1]
    return bool(re.match(r"^WM[A-Z]{2,4}_[^/]+\.php$", path)) \
        and not path.lower().endswith("_main.php")


def parse_navweaps(url: str, html: str,
                   category_display: str = "") -> CatalogEntry | None:
    """Parse a navweaps.com naval-missile detail page."""
    if not html:
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()

    # Country: "... - Naval Missiles of the United States of America - NavWeaps"
    country = ""
    ctry_m = re.search(r"Naval Missiles of ([^-]+)", title, re.I)
    if ctry_m:
        raw = ctry_m.group(1).strip().lower()
        for k, v in _COUNTRY_MAP.items():
            if k in raw:
                country = v
                break

    # Designation: first <h1> inside the content area (skip the site header h1).
    # <br> inside an h1 becomes "; " so multi-line designations stay readable.
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    name = ""
    for h in h1s:
        cand = html_lib.unescape(
            re.sub(r"\s+", " ",
                   re.sub(r"<\s*br\s*/?\s*>", "; ", h, flags=re.I)
                   ).replace("</", "<")).strip()
        cand = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cand)).strip()
        if cand and cand != "NavWeaps":
            name = cand
            break
    if not name:
        # fall back to the first title segment
        name = title.split(" - ")[0].strip()
    if not name or len(name) > 160:
        return None

    # Spec pairs: <table class="prettytable"> rows of <th>Label</th><td>Value</td>
    specs: list[tuple[str, str]] = []
    for tm in re.finditer(
            r'<tr[^>]*>\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>\s*</tr>',
            html, re.S | re.I):
        k = html_lib.unescape(re.sub(r"\s+", " ",
                                     re.sub(r"<[^>]+>", " ", tm.group(1)))).strip(" :")
        v = html_lib.unescape(re.sub(r"\s+", " ",
                                     re.sub(r"<br\s*/?>", "; ", tm.group(2))))
        v = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v)).strip(" ;")
        if k and v and len(k) < 60 and len(v) < 400:
            specs.append((k, v))

    # Description: prose paragraphs after the Description heading.
    desc_paras: list[str] = []
    dm = re.search(r"<h2[^>]*>\s*Description\s*</h2>(.*?)(?:<h2|\Z)",
                   html, re.S | re.I)
    if dm:
        for p in re.findall(r"<p[^>]*>(.*?)</p>", dm.group(1), re.S | re.I):
            text = re.sub(r"\s+", " ",
                          html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
            if len(text) > 80:
                desc_paras.append(text)
            if len(desc_paras) >= 2:
                break
    body = " ".join(desc_paras)[:600]

    if not category_display or category_display == "Uncategorized":
        category_display = _classify_navweaps(name, specs, body)

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country=country,
        manufacturer="",
        category=category_display,
        description=body,
        specs=[f"{k}: {v}" for k, v in specs[:20]],
        sources=[SourceRef("NavWeaps (T. DiGiulian)", url)],
        fetched_at=now_iso(),
    )


def _classify_navweaps(name: str, spec_pairs: list[tuple[str, str]],
                       body: str) -> str:
    """Naval missiles split between SLCM and Rocket-and-missile-weapons.

    Sea-launched cruise missiles: cruise/anti-ship missiles whose launch
    platforms include ships/submarines (the 'Ship Class Used On' row names
    them explicitly on every NavWeaps page). Surface-to-air (Standard,
    Terrier...) and ASW rockets (ASROC) go to Rocket and missile weapons.
    All keyword tests use word boundaries so e.g. "missile cruisers" does
    not read as a cruise-missile marker."""
    import re as _re

    spec_map = {k.lower(): v.lower() for k, v in spec_pairs}
    platforms = spec_map.get("ship class used on", "")
    text = f"{name} {body}".lower()

    def has(pattern: str, s: str) -> bool:
        return bool(_re.search(rf"\b{_re.escape(pattern)}\b", s))

    cruise_markers = (
        "cruise missile", "anti-ship", "antiship", "land-attack", "land attack",
        "tomahawk", "harpoon", "exocet", "otomat", "teseo", "kalibr", "klub",
        "oniks", "yakhont", "brahmos", "moskit", "sunburn", "styx", "silkworm",
        "naval strike missile", "rbs-15", "penguin", "martel", "kelt", "kenel",
        "shaddock", "siren", "ametist", "malakhit", "bazalt", "vulkan",
        "granat",
    )
    sea_platform = ("submarine" in platforms or _re.search(r"\bship\b|\bcruiser\b"
                    r"|\bdestroyer\b|\bfrigate\b|\bcorvette\b|\bboat\b",
                    platforms) is not None)

    if any(has(m, text) or has(m, name.lower()) for m in cruise_markers):
        return "Sea-launched cruise missiles" if (
            sea_platform or not platforms) else \
            "Rocket and missile weapons"

    # Explicit cruise description with a sea launch platform.
    if has("cruise", text) and sea_platform:
        return "Sea-launched cruise missiles"

    return "Rocket and missile weapons"


# Sections on WM*_Main.php index pages that carry inline 4-column data tables
# (Name | Industry Code | NATO Codename | Notes). Section heading (lower-case,
# substring match) -> catalog category. Headings not listed here are skipped
# (e.g. 'Missile Launchers').
NAVWEAPS_MAIN_SECTIONS: list[tuple[str, str]] = [
    ("anti-ship missiles", "Sea-launched cruise missiles"),
    ("strategic missiles", "Rocket and missile weapons"),
    ("anti-aircraft missiles", "Rocket and missile weapons"),
    ("anti-submarine missiles", "Rocket and missile weapons"),
]


def parse_navweaps_main_listing(url: str, html: str) -> list[CatalogEntry]:
    """Parse the inline data tables of a WM*_Main.php index page.

    Some country indexes (notably Russia/USSR) print whole weapon tables on
    the index itself instead of per-missile detail pages. Each table row
    becomes one entry: designation from col0, industry code + NATO codename
    into alt_names/specs, notes into description."""
    out: list[CatalogEntry] = []
    if not html:
        return out

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip() \
        if title_m else ""
    country = ""
    ctry_m = re.search(r"Naval Missiles of ([^-]+)", title, re.I)
    if ctry_m:
        raw = ctry_m.group(1).strip().lower()
        for k, v in _COUNTRY_MAP.items():
            if k in raw:
                country = v
                break

    body = html[html.find("<body"):]
    sections = re.split(r"<h2[^>]*>", body)[1:]
    for sec in sections:
        head_m = re.match(r"(.*?)</h2>", sec, re.S | re.I)
        if not head_m:
            continue
        head = re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<[^>]+>", "", head_m.group(1)))).strip().lower()
        category = next((cat for key, cat in NAVWEAPS_MAIN_SECTIONS
                         if key in head), None)
        if not category:
            continue
        rest = sec[head_m.end():]
        table_m = re.search(r"<table[^>]*>(.*?)</table>", rest, re.S | re.I)
        if not table_m:
            continue
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(1),
                             re.S | re.I):
            tds = [html_lib.unescape(re.sub(
                r"\s+", " ",
                re.sub(r"<\s*br\s*/?\s*>", "; ", td, flags=re.I)
            )).strip() for td in re.findall(
                r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
            tds = [re.sub(r"<[^>]+>", "", td).strip(" ;") for td in tds]
            if len(tds) < 3 or not tds[0]:
                continue
            name, industry, nato = tds[0], tds[1], tds[2]
            notes = tds[3] if len(tds) > 3 else ""
            if len(name) > 80 or name.lower() == "name":
                continue
            alt_names = [a for a in (nato if nato.lower() != "n/a" else "",
                                     industry) if a]
            specs = []
            if nato and nato.lower() != "n/a":
                specs.append(f"NATO Codename: {nato}")
            if industry:
                specs.append(f"Industry Code: {industry}")
            out.append(CatalogEntry(
                designation=name,
                alt_names=alt_names[:4],
                country=country or "Russia/USSR",
                manufacturer="",
                category=category,
                description=(notes or
                             f"{name} — naval missile listed by NavWeaps.")[:400],
                specs=specs[:6],
                sources=[SourceRef("NavWeaps (T. DiGiulian)", url)],
                fetched_at=now_iso(),
            ))
    return out
