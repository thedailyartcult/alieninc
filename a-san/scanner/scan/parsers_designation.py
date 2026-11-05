"""Parser for designation-systems.net - Andreas Parsch's directory of US military
rockets and missiles (designation-systems.net/dusrm/m-NN.html).

robots.txt: User-agent:* allowed for /dusrm/ and /usmilav/. No crawl-delay.
Content licence: (c) Andreas Parsch, all rights reserved — fact-extraction only,
every entry carries the source URL. See POLICY.md.
"""
from __future__ import annotations

import html as html_lib
import re

from .config import classify_path
from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.designation-systems.net"


def parse_designation_listing(html: str, base_url: str = "https://www.designation-systems.net/usmilav/missiles.html") -> list[tuple[str, str, str]]:
    """Parse the /usmilav/missiles.html catalog table.

    Returns [(detail_url, designation, manufacturer), ...] for every missile
    row in the main catalog table. The listing groups rows under <h2> section
    headings (Missiles / Rockets / Probes / Boosters / Satellites); we keep
    only the Missiles and Rockets sections — the others are not catalog
    equipment.
    """
    if not html:
        return []
    out: list[tuple[str, str, str]] = []
    # Each row: <td><b><a href="../dusrm/m-NN.html">DESIGNATION</a>...</b></td>
    #   <td>MANUFACTURER</td> <td>NAME (REMARKS)</td> <td>PREV</td>
    row_re = re.compile(
        r'<tr>\s*<td[^>]*>\s*<b>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>'
        r'.*?</b>\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        re.S | re.I,
    )
    for m in row_re.finditer(html):
        href = html_lib.unescape(m.group(1))
        designation = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        manufacturer = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        name_field = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(4))).strip()
        # Resolve relative href to absolute
        if href.startswith("../"):
            abs_url = f"https://{_HOST}/{href[3:]}"
        elif href.startswith("/"):
            abs_url = f"https://{_HOST}{href}"
        elif href.startswith("http"):
            abs_url = href
        else:
            abs_url = f"https://{_HOST}/{href}"
        # Use name in parentheses as alt name (e.g. "AIM-9 Sidewinder")
        alt = ""
        paren_m = re.search(r"\(([^)]+)\)\s*$", name_field) or re.search(
            r"<i>([^<]+)</i>", name_field)
        if alt:
            pass
        # If the designation cell has the popular name in <i>, capture it
        if not alt:
            i_m = re.search(r"<i>([^<]+)</i>", m.group(2))
            if i_m:
                alt = html_lib.unescape(i_m.group(1)).strip()
        out.append((abs_url, designation, manufacturer))
    return out


def parse_designation(url: str, html: str, category_display: str = "") -> CatalogEntry | None:
    """Parse a designation-systems.net/dusrm/m-NN.html detail page."""
    if not html:
        return None

    # <title>Raytheon AIM-9 Sidewinder</title> — cleanest name
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
    if not title or title.lower().startswith(("404", "not found")):
        return None

    # <h1 style="text-align:center">MANUFACTURER <b>DESIGNATION</b> <i>PopularName</i></h1>
    h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    designation = title
    manufacturer = ""
    alt_name = ""
    if h1_m:
        h1 = h1_m.group(1)
        b_m = re.search(r"<b>(.*?)</b>", h1, re.S | re.I)
        i_m = re.search(r"<i>(.*?)</i>", h1, re.S | re.I)
        if b_m:
            designation = html_lib.unescape(re.sub(r"<[^>]+>", "", b_m.group(1))).strip()
        if i_m:
            alt_name = html_lib.unescape(re.sub(r"<[^>]+>", "", i_m.group(1))).strip()
        # Manufacturer is the plain text before the <b> designation
        pre = re.split(r"<b>", h1, maxsplit=1, flags=re.I)[0]
        manufacturer = html_lib.unescape(re.sub(r"<[^>]+>", "", pre)).strip().rstrip(",(").strip()

    # Description: <div class="content"> ... <p>paragraphs</p> ...
    # Take all <p> blocks between <div class="content"> and the first
    # <h2>Specifications</h2> heading (the body prose region).
    content_start_m = re.search(r'<div\s+class="content"[^>]*>', html, re.I)
    body = ""
    if content_start_m:
        region = html[content_start_m.end():]
        spec_h = re.search(r"<h2[^>]*>\s*Specifications\s*</h2>", region, re.I)
        text_region = region[:spec_h.start()] if spec_h else region[:30000]
        paras = re.findall(r"<p[^>]*>(.*?)</p>", text_region, re.S | re.I)
        body = " ".join(
            re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
            for p in paras if p.strip()
        ).strip()
    if not body:
        body = f"US military rocket/missile entry: {designation}"
        if alt_name:
            body += f" ({alt_name})"

    # Spec table: <table class="specs-table"> with first row = variant headers,
    # subsequent rows = <tr><td>Param</td><td>Value</td>...</tr>
    specs: list[str] = []
    spec_table_m = re.search(
        r'<table\s+class="specs-table"[^>]*>(.*?)</table>', html, re.S | re.I)
    if spec_table_m:
        table_html = spec_table_m.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
        # First row is variant headers (<th>...)
        variant_headers: list[str] = []
        if rows:
            ths = re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S | re.I)
            variant_headers = [html_lib.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                               for t in ths]
        for row in rows[1:]:
            tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            if not tds:
                continue
            cells = [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in tds]
            param = cells[0]
            if not param:
                continue
            # Join variant values; if there's only one value column, simple "Param: Value"
            values = [c for c in cells[1:] if c]
            if not values:
                continue
            if len(values) == 1:
                specs.append(f"{param}: {values[0]}")
            else:
                # Multi-variant: emit one spec per variant
                for vh, v in zip(variant_headers, values):
                    if vh and v:
                        specs.append(f"{param} ({vh}): {v}")

    # Category: the site is US-only missiles & rockets. Air-launched vs SLCM vs
    # rocket/missile is best inferred from the designation prefix.
    if not category_display or category_display == "Uncategorized":
        category_display = _classify_designation(designation, alt_name, body)

    return CatalogEntry(
        designation=designation,
        alt_names=[alt_name] if alt_name else [],
        country="USA",
        manufacturer=manufacturer,
        category=category_display,
        description=body[:600],
        specs=specs[:20],
        sources=[SourceRef("Designation-Systems.net", url)],
        fetched_at=now_iso(),
    )


def _classify_designation(designation: str, alt_name: str, body: str) -> str:
    """Map a designation-systems.net entry to a catalog category by designation prefix.

    The site covers US military rockets and missiles, so the choices narrow to:
    Air-launched munitions, Sea-launched cruise missiles, Rocket and missile weapons.
    """
    text = f"{designation} {alt_name} {body}".upper()
    d = designation.upper()
    # Air-launched
    if d.startswith(("AIM-", "AGM-", "GAM-", "AAM-", "ASROC")) or "AIR-LAUNCHED" in text:
        return "Air-launched munitions"
    # Sea-launched cruise missiles (submarine/ship-launched)
    if d.startswith(("BGM-", "RGM-", "UGM-", "RUR-")) or "SUBMARINE-LAUNCHED" in text \
            or "SEA-LAUNCHED" in text or "SLCM" in text:
        return "Sea-launched cruise missiles"
    # Default for the rest (MGM-, LGM-, PGM-, ballistic, SAM, rockets, probes)
    return "Rocket and missile weapons"
