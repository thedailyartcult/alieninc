"""Parser for fas.org (Federation of American Scientists) — man.fas.org/dod-101/.

robots.txt: User-agent:* with Disallow: (empty — nothing disallowed). No
crawl-delay. Sitemap: https://fas.org/sitemap_index.xml.
Content licence: FAS is a 501(c)(3) nonprofit; equipment pages carry no
prominent copyright notice. Historically permissive for noncommercial/
educational use. Fact-extraction with attribution — see POLICY.md.

Equipment indexes (all 200 OK):
  /dod-101/sys/land/     — 379 land vehicle/equipment pages
  /dod-101/sys/ship/     — 166 ship pages
  /dod-101/sys/ac/equip/ — 245 aircraft-equipment pages

Two spec-table patterns (both regex-parseable):
  1. Single-column (Stinger): <td width=30%><B>Label</b></td><td>Value</td>
  2. Multi-variant (M1 Abrams): <td><strong><big>Label:</big></strong></td>
     <td><strong><big>Value</big></strong></td> ... (variant headers in first row)
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "man.fas.org"
_FAS_BASE = "https://man.fas.org/dod-101/sys"

# Equipment index URLs for discovery
FAS_INDEX_URLS = [
    f"{_FAS_BASE}/land/",
    f"{_FAS_BASE}/ship/",
    f"{_FAS_BASE}/ac/equip/",
]


def parse_fas_listing(html: str, base_url: str) -> list[str]:
    """Parse a FAS equipment index page for detail-page URLs.

    Returns [detail_url, ...]. Links are relative like 'm1.htm', 'cvn-68.htm'.
    """
    if not html:
        return []
    out: list[str] = []
    # <a href="m1.htm">M1 Abrams</a> — relative .htm links
    link_re = re.compile(r'<a\s+href="([a-z0-9_+-]+\.htm)"[^>]*>', re.I)
    for m in link_re.finditer(html):
        href = html_lib.unescape(m.group(1)).strip()
        if href.endswith(".htm") and not href.startswith(("index", "intro", "refs")):
            out.append(base_url.rstrip("/") + "/" + href)
    # Dedupe preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def parse_fas(url: str, html: str, category_display: str = "") -> CatalogEntry | None:
    """Parse a FAS equipment detail page (man.fas.org/dod-101/sys/.../<name>.htm)."""
    if not html:
        return None

    # <title>M1 Abrams Main Battle Tank</title> or
    # <title>FIM-92A Stinger Weapons System: RMP &amp; Basic</title>
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
    # Strip common suffixes
    title = re.sub(r"\s*[-–]\s*(Navy Ships|Army|Air Force|Missiles|Guns|Land|AC|\w+\s*Systems?)\s*$",
                   "", title, flags=re.I).strip()
    if not title:
        return None

    # Try to find an <h1> for a potentially cleaner name — but only if it's
    # NOT a generic heading like "Specifications" (which is the spec-table h1)
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if h1_m:
        h1 = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).strip()
        # Reject generic headings that come from the spec table, not the page title
        if h1 and len(h1) < 100 and h1.lower() not in (
                "specifications", "specs", "general", "description"):
            title = h1

    # --- Spec extraction: try both patterns ---

    specs: list[str] = []

    # Pattern 1 (Stinger-style): <td ...width=30%...><B>Label</b></td><td>Value</td>
    p1_re = re.compile(
        r'<td[^>]*width\s*=\s*["\']?30%[^>]*>\s*<b>\s*([^<]+?)\s*</b>\s*</td>\s*'
        r'<td[^>]*>(.*?)</td>',
        re.S | re.I)
    for m in p1_re.finditer(html):
        label = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        value = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        value = re.sub(r"\s+", " ", value)
        if label and value and len(label) < 50:
            # Extract manufacturer/country from specific fields
            ll = label.lower()
            if ll in ("manufacturer", "contractor") and not category_display:
                pass  # handled below
            specs.append(f"{label}: {value}")

    # Pattern 2 (M1 Abrams-style): multi-variant table with
    # <td><strong><big>Label:</big></strong></td><td><strong><big>Value</big></strong></td>
    if not specs:
        # Find the variant header row: <td><strong><big>M1/IPM1</big></strong></td>...
        # Then each subsequent row: <td><strong><big>Length:</big></strong></td><td>val</td>...
        p2_table_re = re.compile(
            r'<table[^>]*border[^>]*>.*?</table>', re.S | re.I)
        for tbl_m in p2_table_re.finditer(html):
            tbl = tbl_m.group(0)
            # Check if this is a spec table (has <big> tags with labels)
            if "<big>" not in tbl.lower():
                continue
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I)
            if not rows:
                continue
            # First row = variant headers
            variant_hdrs = re.findall(
                r"<(?:strong|b)>\s*<big>\s*([^<]+?)\s*</big>\s*</(?:strong|b)>",
                rows[0], re.S | re.I)
            variant_hdrs = [h.strip() for h in variant_hdrs if h.strip()]
            for row in rows[1:]:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
                if not cells:
                    continue
                # First cell = label (with <strong><big>Label:</big></strong>)
                label_html = cells[0]
                label = html_lib.unescape(re.sub(r"<[^>]+>", "", label_html)).strip().rstrip(":")
                if not label:
                    continue
                # Remaining cells = values (one per variant)
                values = []
                for c in cells[1:]:
                    v = html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                    v = re.sub(r"&nbsp;", " ", v)
                    v = re.sub(r"\s+", " ", v).strip()
                    if v and v != "&nbsp;":
                        values.append(v)
                if not values:
                    continue
                if len(values) == 1 or not variant_hdrs:
                    specs.append(f"{label}: {values[0]}")
                else:
                    for vh, v in zip(variant_hdrs, values):
                        if vh and v:
                            specs.append(f"{label} ({vh}): {v}")

    # --- Description: first <p> blocks in the main content ---
    body = ""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
    candidates = []
    for p in paras:
        text = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
        if len(text) > 50 and not text.lower().startswith(("source:", "references:", "click here")):
            candidates.append(text)
        if len(candidates) >= 3:
            break
    body = " ".join(candidates)
    if not body:
        body = f"FAS equipment profile: {title}"

    # --- Category classification from URL path ---
    if not category_display or category_display == "Uncategorized":
        category_display = _classify_fas(url, title, specs)

    # --- Extract manufacturer from specs if present ---
    manufacturer = ""
    for s in specs:
        if s.lower().startswith(("manufacturer:", "contractor:", "prime -", "prime:")):
            manufacturer = s.split(":", 1)[1].strip() if ":" in s else s
            break

    return CatalogEntry(
        designation=title,
        alt_names=[],
        country="",  # FAS pages don't have a structured country field
        manufacturer=manufacturer,
        category=category_display,
        description=body[:500],
        specs=specs[:25],
        sources=[SourceRef("FAS (Federation of American Scientists)", url)],
        fetched_at=now_iso(),
    )


def _classify_fas(url: str, title: str, specs: list[str]) -> str:
    """Classify a FAS equipment page into an A-SAN category by URL path + title."""
    url_lower = url.lower()
    title_lower = title.lower()
    spec_text = " ".join(specs).lower()

    # URL path is the strongest signal
    if "/sys/ship/" in url_lower:
        # Ship equipment vs ship weapons
        if any(kw in title_lower for kw in ("missile", "torpedo", "gun", "cwiz", "phalanx",
                                              "sam", "vls", "railgun", "ciws")):
            # Naval weapons — could be SLCM or rocket/missile
            if "cruise" in title_lower or "slcm" in title_lower or "tomahawk" in title_lower:
                return "Sea-launched cruise missiles"
            return "Rocket and missile weapons"
        return "Naval vessels"

    if "/sys/ac/equip/" in url_lower:
        # Aircraft equipment — could be EW, sensors, or munitions
        if any(kw in title_lower for kw in ("jammer", "electronic warfare", "ew ", "ecm",
                                              "sigint", "elint", "countermeasure")):
            return "EW assets"
        if any(kw in title_lower for kw in ("radar", "awacs", "sensor", "sonar")):
            return "EW assets"
        if any(kw in title_lower for kw in ("missile", "bomb", "munition", "amraam", "sidewinder",
                                              "aim-", "agm-", "jdam")):
            return "Air-launched munitions"
        # Other aircraft equipment (engines, avionics) — best fit is Aircraft
        return "Aircraft"

    if "/sys/land/" in url_lower:
        # Land systems: armored, automotive, UGV, small arms, missiles, EW
        if any(kw in title_lower for kw in ("ugv", "unmanned ground", "robot", "talon", "packbot",
                                              "gladiator")):
            return "UGVs"
        if any(kw in title_lower for kw in ("stinger", "patriot", "javelin", "tow", "atgm",
                                              "missile", "sam ", "air defense", "rocket")):
            return "Rocket and missile weapons"
        if any(kw in title_lower for kw in ("truck", "hmwwv", "hmmwv", "humvee", "lav",
                                              "logistic", "cargo", "transport vehicle")):
            return "Automotive vehicles"
        if any(kw in title_lower for kw in ("rifle", "pistol", "machine gun", "grenade",
                                              "carbine", "shotgun", "sniper")):
            return "Small arms"
        if any(kw in title_lower for kw in ("jammer", "electronic warfare", "ew ", "ecm",
                                              "countermeasure", "sigint")):
            return "EW assets"
        # Default for land: armored vehicles (tanks, IFVs, APCs)
        if any(kw in title_lower for kw in ("tank", "mbt", "ifv", "apc", "armored", "armoured",
                                              "bradley", "abrams", "leopard", "stryker",
                                              "vehicle", "combat")):
            return "Armored vehicles and equipment"
        # If it has truck/logistic specs, automotive; otherwise armored
        if any(kw in spec_text for kw in ("payload", "cargo", "logistic")):
            return "Automotive vehicles"
        return "Armored vehicles and equipment"

    return "Armored vehicles and equipment"
