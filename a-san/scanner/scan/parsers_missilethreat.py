"""Parser for missilethreat.csis.org — CSIS Missile Defense Project "Missiles of
the World" database.

robots.txt: User-agent:* allowed (Disallow: empty). Crawl-delay: 10.
Content licence: (c) CSIS, all rights reserved — fact-extraction only, every
entry carries the source URL AND the CSIS "Cite this Page" citation string for
clean attribution. See POLICY.md.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "missilethreat.csis.org"


def parse_missilethreat_listing(html: str) -> list[tuple[str, str]]:
    """Parse the /missile/ archive page's alphabetical dropdown.

    Returns [(detail_url, display_name), ...] — one per missile. The dropdown
    <select id="item-select"> is the canonical full catalog enumeration.
    """
    if not html:
        return []
    out: list[tuple[str, str]] = []
    opt_re = re.compile(
        r'<option\s+value="(https?://[^"]+)"[^>]*class="[^"]*component-select__option[^"]*"[^>]*>([^<]+)</option>',
        re.I,
    )
    for m in opt_re.finditer(html):
        url = html_lib.unescape(m.group(1)).strip()
        name = html_lib.unescape(m.group(2)).strip()
        if url and name and not url.startswith("#"):
            out.append((url, name))
    return out


def parse_missilethreat(url: str, html: str, category_display: str = "") -> CatalogEntry | None:
    """Parse a missilethreat.csis.org/missile/<slug>/ detail page."""
    if not html:
        return None

    # <h1 class="single__header-title">Agni-I</h1>
    h1_m = re.search(r'<h1[^>]*class="[^"]*single__header-title[^"]*"[^>]*>(.*?)</h1>',
                     html, re.S | re.I)
    if not h1_m:
        # fallback to <title>
        t_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if not t_m:
            return None
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", t_m.group(1))).strip()
        name = re.sub(r"\s*-\s*Missile Threat.*$", "", name, flags=re.I).strip()
    else:
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).strip()
    if not name:
        return None

    # Spec block: <dl class="at-a-glance__spec"><dt class="...">Label</dt><dd>Value</dd></dl>
    spec_pairs: list[tuple[str, str]] = []
    dl_re = re.compile(
        r'<dl[^>]*class="[^"]*at-a-glance__spec[^"]*"[^>]*>(.*?)</dl>', re.S | re.I)
    dt_re = re.compile(
        r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', re.S | re.I)
    for dl_m in dl_re.finditer(html):
        dl_body = dl_m.group(1)
        for dt_m in dt_re.finditer(dl_body):
            label = html_lib.unescape(re.sub(r"<[^>]+>", "", dt_m.group(1))).strip()
            value = html_lib.unescape(re.sub(r"<[^>]+>", "", dt_m.group(2))).strip()
            label = re.sub(r"\s+", " ", label)
            value = re.sub(r"\s+", " ", value)
            if label and value:
                spec_pairs.append((label, value))

    country = ""
    manufacturer = ""
    specs: list[str] = []
    for label, value in spec_pairs:
        ll = label.lower()
        if ll in ("originated from", "possessed by", "origin"):
            if not country:
                country = value
        elif ll in ("class",):
            specs.insert(0, f"Class: {value}")
        else:
            specs.append(f"{label}: {value}")
    if not country:
        # Try the breadcrumb country link
        bc_m = re.search(r'<li>\s*<a\s+href=[\'"]/country/[^\'"]+[\'"][^>]*>([^<]+)</a>\s*</li>',
                         html, re.I)
        if bc_m:
            country = html_lib.unescape(bc_m.group(1)).strip()

    # Description: <div class="single__content"> ... first <p class="wp-block-paragraph">
    body = ""
    content_m = re.search(
        r'<div[^>]*class="[^"]*single__content[^"]*"[^>]*>(.*?)</div>\s*<(?:footer|section|aside|div[^>]*class="[^"]*(?:related|footnotes))',
        html, re.S | re.I)
    if content_m:
        body_html = content_m.group(1)
        paras = re.findall(
            r'<p[^>]*class="[^"]*wp-block-paragraph[^"]*"[^>]*>(.*?)</p>',
            body_html, re.S | re.I)
        if not paras:
            paras = re.findall(r"<p[^>]*>(.*?)</p>", body_html, re.S | re.I)
        body = " ".join(
            re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
            for p in paras[:3] if p.strip()
        ).strip()
    if not body:
        body = f"CSIS Missile Threat profile: {name}"

    # CSIS "Cite this Page" citation — store verbatim in the description tail
    # for clean attribution since CSIS is all-rights-reserved.
    cite_m = re.search(
        r'<span[^>]*class="[^"]*cite__citation[^"]*"[^>]*>(.*?)</span>', html, re.S | re.I)
    citation = ""
    if cite_m:
        citation = re.sub(r"\s+", " ",
                          html_lib.unescape(re.sub(r"<[^>]+>", "", cite_m.group(1)))
                          ).strip()

    # Last-updated date (for recency scoring)
    date_m = re.search(
        r'<div[^>]*class="[^"]*post-meta__date[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I)
    last_updated = ""
    if date_m:
        last_updated = html_lib.unescape(re.sub(r"<[^>]+>", "", date_m.group(1))).strip()

    # Category: CSIS "Missiles of the World" covers cruise + ballistic + air-defense.
    # Class field tells us basing (air/sea/land); SLCM needs the Basing or Class.
    if not category_display or category_display == "Uncategorized":
        category_display = _classify_missile(name, spec_pairs, body)

    description = body[:500]
    if citation:
        description = f"{description} [Source: {citation}]"

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country=country,
        manufacturer=manufacturer,
        category=category_display,
        description=description,
        specs=specs[:20],
        sources=[SourceRef("Missile Threat (CSIS)", url)],
        fetched_at=now_iso(),
    )


def _classify_missile(name: str, spec_pairs: list[tuple[str, str]], body: str) -> str:
    """Classify a CSIS missile entry into a catalog category."""
    spec_map = {k.lower(): v for k, v in spec_pairs}
    cls = spec_map.get("class", "").lower()
    basing = spec_map.get("basing", "").lower()
    text = f"{name} {body} {cls} {basing}".lower()

    # Sea-launched cruise missiles
    if "sea-launched" in text or "submarine-launched" in text \
            or "slcm" in text or "ship-based" in text \
            or "submarine" in basing or "ship" in basing:
        if "cruise" in cls or "cruise" in text:
            return "Sea-launched cruise missiles"
        # Submarine-launched ballistic = naval vessel weapon but our category is SLCM only
        return "Sea-launched cruise missiles"

    # Air-launched munitions
    if "air-launched" in text or "air-to-air" in text or "air-to-surface" in text \
            or "air-breathing" in cls and "air-launched" in text:
        return "Air-launched munitions"

    # Everything else (ballistic, SAM, ground-launched cruise, hypersonic) → Rocket and missile weapons
    return "Rocket and missile weapons"
