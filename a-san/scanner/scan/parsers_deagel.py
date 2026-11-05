"""Parser for deagel.com — military equipment component pages with structured specs.

robots.txt: User-agent:* Allow: / (only /cgi-bin/ disallowed). No crawl-delay.
Content: © all-rights-reserved (fact-extraction-only per POLICY.md).

Deagel.com has 1,907 equipment components across categories like Countermeasures,
Decoy Systems, ESM & Warning Systems, Jamming Systems, Radar Systems, etc.
Individual component pages render server-side (Blazor SSR) with structured spec
tables in HTML <td> elements.

Page structure (from HTML analysis):
- <title>: Equipment designation
- Table rows with <td> cells containing:
  - Model variants: [designation, status, year, produced]
  - Operators: [country, status, quantity, notes]
  - Specifications: [spec_name, spec_value]
  - Group, Status, Origin, Contractor, IOC, Total Production, Unitary Cost
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.deagel.com"


def _clean(text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_deagel(url: str, html_text: str) -> CatalogEntry | None:
    """Parse a deagel.com component page with structured spec tables.

    Extracts designation, status, origin, contractor, specs, operators, and
    model variants from the HTML table structure.
    """
    if not html_text:
        return None

    # <title>AN/ALE-50</title> — may be empty on Blazor SSR pages
    title_m = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    title = _clean(title_m.group(1)) if title_m else ""
    # Fallback: <h1> tags (Blazor SSR renders these)
    if not title or len(title) < 2:
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S | re.I)
        if h1_m:
            title = _clean(h1_m.group(1))
    if not title or len(title) < 2:
        return None

    # Extract all <td> cells
    tds = re.findall(r"<td[^>]*>(.*?)</td>", html_text, re.S | re.I)
    cells = [_clean(td) for td in tds if _clean(td)]

    if len(cells) < 3:
        return None

    # The first cell is typically the designation
    designation = cells[0]
    if not designation or len(designation) < 2:
        return None

    # Extract structured fields from the page HTML
    # Deagel.com uses <p> tags with <br/> separators:
    # Origin : <b>United States</b> <br/>Contractor : Raytheon <br/>IOC : 1996
    country = ""
    manufacturer = ""
    status = ""
    ioc = ""
    total_production = ""
    unitary_cost = ""
    group = ""
    description = ""

    # Extract the spec paragraph(s) — look for Origin/Contractor/IOC pattern
    spec_block = ""
    p_blocks = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S | re.I)
    for pb in p_blocks:
        if "Origin" in pb and ("Contractor" in pb or "IOC" in pb):
            spec_block = _clean(pb)
            break

    if spec_block:
        # Parse Origin
        origin_m = re.search(r"Origin\s*:\s*(.*?)(?:\s*Contractor|\s*$)", spec_block, re.I)
        if origin_m:
            country = origin_m.group(1).strip()
        # Parse Contractor
        contractor_m = re.search(r"Contractor\s*:\s*(.*?)(?:\s*Initial|\s*Total|\s*$)", spec_block, re.I)
        if contractor_m:
            manufacturer = contractor_m.group(1).strip()
        # Parse IOC
        ioc_m = re.search(r"Initial Operational Capability.*?\)\s*:\s*(\d{4})", spec_block, re.I)
        if ioc_m:
            ioc = ioc_m.group(1)
        # Parse Total Production
        tp_m = re.search(r"Total Production\s*:\s*([\d,]+)", spec_block, re.I)
        if tp_m:
            total_production = tp_m.group(1)
        # Parse Unitary Cost
        cost_m = re.search(r"Unitary Cost\s*:\s*(USD\s*\$[\d,]+)", spec_block, re.I)
        if cost_m:
            unitary_cost = cost_m.group(1)
        # Parse Group
        group_m = re.search(r"Group\s*:\s*(.*?)(?:\s*Status|\s*$)", spec_block, re.I)
        if group_m:
            group = group_m.group(1).strip()
        # Parse Status
        status_m = re.search(r"Status\s*:\s*(\w[\w\s]*?)(?:\s*(?:Also|Origin|Contractor)|\s*$)", spec_block, re.I)
        if status_m:
            status = status_m.group(1).strip()

    # Also try raw HTML for fields not in the spec block
    if not country:
        origin_m = re.search(r"Origin\s*:\s*<[^>]+><b>([^<]+)</b>", html_text, re.I)
        if origin_m:
            country = _clean(origin_m.group(1))
    if not manufacturer:
        contractor_m = re.search(r"Contractor\s*:\s*([^<\n]+)", html_text, re.I)
        if contractor_m:
            manufacturer = _clean(contractor_m.group(1))
    if not ioc:
        ioc_m = re.search(r"Initial Operational Capability.*?\)\s*:\s*(\d{4})", html_text, re.I)
        if ioc_m:
            ioc = ioc_m.group(1)

    # Description: first long <p> after the h1 designation heading
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S | re.I)
    for p in paras:
        text = _clean(p)
        if len(text) > 80 and not text.lower().startswith(("copyright", "this website", "loading")):
            description = text
            break

    # Build specs list
    specs: list[str] = []
    if group:
        specs.append(f"Group: {group}")
    if status:
        specs.append(f"Status: {status}")
    if ioc:
        specs.append(f"IOC: {ioc}")
    if total_production:
        specs.append(f"Total Production: {total_production}")
    if unitary_cost:
        specs.append(f"Unitary Cost: {unitary_cost}")
    if country:
        specs.append(f"Origin: {country}")
    if manufacturer:
        specs.append(f"Contractor: {manufacturer}")

    # Extract specification rows (name/value pairs in consecutive cells)
    spec_names = (
        "Service Life", "Mission Endurance", "Frequency", "Range",
        "Weight", "Length", "Diameter", "Speed", "Altitude",
        "Operating Temperature", "Power", "Detection Range",
    )
    for i, cell in enumerate(cells):
        for sn in spec_names:
            if cell.strip().lower() == sn.lower() and i + 1 < len(cells):
                specs.append(f"{sn}: {cells[i + 1]}")

    # Classify into A-SAN category
    category = _classify_deagel(group, designation, description, " ".join(cells))

    return CatalogEntry(
        designation=designation,
        alt_names=[],
        country=country or "Unknown",
        manufacturer=manufacturer,
        category=category,
        description=(description or f"Deagel.com component: {designation}")[:500],
        specs=specs[:25],
        sources=[SourceRef("Deagel.com (all-rights-reserved)", url)],
        fetched_at=now_iso(),
    )


def _classify_deagel(group: str, designation: str, description: str, text: str) -> str:
    """Classify a deagel.com component into an A-SAN category."""
    combined = f"{group} {designation} {description} {text}".lower()

    # EW assets
    ew_groups = (
        "countermeasures", "decoy systems", "esm", "warning systems",
        "jamming systems", "radar systems", "electronic warfare",
    )
    ew_keywords = (
        "electronic warfare", "electronic countermeasure", "jammer", "jamming",
        "ecm", "eccm", "sigint", "elint", "comint", "radar warning", "rwr",
        "countermeasure", "decoy", "chaff", "flare", "ircm", "dircm",
        "an/alq", "an/ale", "an/alr", "an/alt", "an/slr", "an/slq",
    )
    if any(g in combined for g in ew_groups) or any(k in combined for k in ew_keywords):
        return "EW assets"

    # Rocket and missile weapons
    if any(kw in combined for kw in ("missile", "rocket", "sam ", "air defense",
                                      "ballistic", "cruise", "atgm", "torpedo")):
        return "Rocket and missile weapons"

    # Aircraft
    if any(kw in combined for kw in ("aircraft", "helicopter", "fighter",
                                      "turbofan", "turboprop", "turboshaft")):
        return "Aircraft"

    # Naval vessels
    if any(kw in combined for kw in ("ship", "vessel", "frigate", "destroyer",
                                      "submarine", "naval gun")):
        return "Naval vessels"

    # Armored vehicles
    if any(kw in combined for kw in ("armor", "vehicle", "tank", "apc", "ifv")):
        return "Armored vehicles and equipment"

    # Default: EW assets (this source is EW-focused)
    return "EW assets"
