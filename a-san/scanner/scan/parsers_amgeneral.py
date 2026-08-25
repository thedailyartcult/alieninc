"""Parser for amgeneral.com — AM General tactical wheeled vehicles.

robots.txt (verified live 2026-08-25): present but EMPTY body (200, zero
bytes) → allow-all by convention; no Crawl-delay. Content licence:
© AM General — fact-extraction with attribution (see POLICY.md §2):
designation + factual specs + short description + exact source URL.

Catalog enumeration: https://www.amgeneral.com/sitemap_index.xml ->
page-sitemap.xml, filter /what-we-do/vehicles-chassis/<slug>/ plus a few
top-level campaign pages (humvee-40, ironclad-humvee-2-ct).

Page structure (verified 2026-08-25 on Humvee 4-CT, WordPress/X theme):
  - designation in <title> / og:title ("Humvee 4-CT")
  - spec sections labelled by <span class="beachwood-wide">SECTION</span>
    (GVW, PAYLOAD, MOBILITY, POWERTRAIN, ELECTRICAL, OPTIONS...) each
    followed by a content div of <p>/<br>-separated lines
  - description in meta name="description"
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

# Curated vehicle pages from page-sitemap.xml (verified 2026-08-25).
AMGENERAL_VEHICLE_PATHS = (
    "/what-we-do/vehicles-chassis/humvee-2ct/",
    "/what-we-do/vehicles-chassis/humvee-2ct-ambulance/",
    "/what-we-do/vehicles-chassis/humvee-2ct-hawkeye-mhs/",
    "/what-we-do/vehicles-chassis/humvee-4ct/",
    "/what-we-do/vehicles-chassis/humvee-4ct-fastback/",
    "/what-we-do/vehicles-chassis/humvee-4ct-armored-fastback-tow/",
    "/what-we-do/vehicles-chassis/humvee-saber/",
    "/what-we-do/vehicles-chassis/humvee-secm/",
    "/what-we-do/vehicles-chassis/mimic-v/",
    "/what-we-do/vehicles-chassis/jltv-a2-2/",
    "/what-we-do/vehicles-chassis/chassis/",
    "/what-we-do/vehicles-chassis/155mm-mobile-artillery-concept/",
    "/humvee-40/",
    "/ironclad-humvee-2-ct/",
)


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_amgeneral(url: str, html: str,
                    category_display: str = "Automotive vehicles") \
        -> CatalogEntry | None:
    """Parse an amgeneral.com vehicle page."""
    if not html or "amgeneral.com" not in url:
        return None

    # --- designation ---
    name = ""
    m = re.search(r'property="og:title"\s+content="([^"]+)"', html, re.I) \
        or re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        name = _clean(m.group(1))
    if not name or len(name) > 100:
        return None

    # --- specs: beachwood-wide section headers + following content block ---
    specs: list[str] = []
    pattern = re.compile(
        r'class="beachwood-wide">([^<]{2,40})</span>'      # section label
        r'.{0,400}?'                                        # wrapper markup
        r'class="x-text x-content[^"]*">(.*?)</div>',       # content until </div>
        re.S)
    for label, body in pattern.findall(html):
        label = _clean(label).upper()
        if not label or label in ("DOWNLOAD", "MISSION"):
            continue
        lines = [ln for ln in re.split(r"<br\s*/?>|</p>\s*<p>|\n", body)]
        count = 0
        for ln in lines:
            ln = _clean(ln)
            if not ln or len(ln) > 200 or ln.endswith(":"):
                continue
            specs.append(f"{label}: {ln}")
            count += 1
            if count >= 10:
                break

    if not specs:
        return None

    # --- description ---
    desc = ""
    m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if m:
        desc = html_lib.unescape(m.group(1)).strip()
    if not desc:
        desc = f"AM General {name}"

    return CatalogEntry(
        designation=name,
        alt_names=["HMMWV"] if "humvee" in name.lower() else [],
        country="United States",
        manufacturer="AM General",
        category=category_display,
        description=desc[:500],
        specs=specs,
        sources=[SourceRef("AM General product page", url)],
        fetched_at=now_iso(),
    )
