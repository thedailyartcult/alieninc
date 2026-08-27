"""Parser for modernfirearms.net — Maxim Popenker's encyclopedia of firearms.

robots.txt: User-agent:* allowed for /en/. Crawl-delay: 20.
Content licence: (c) Maxim Popenker 1999-2026, all rights reserved —
fact-extraction only, every entry carries the source URL. See POLICY.md.

URL discovery note: the bare category slugs (/en/assault-rifles/, /en/handguns/,
/en/shotguns/) 301-redirect to /bez-rubriki/<slug>/ which 404s. Use the
long-slug category URLs from the English nav menu (see MODERNFIREARMS_SEED_URLS
below). Detail pages under /en/<cat>/<country>-<cat>/<slug>/ are live.
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "modernfirearms.net"

# Working English-language category index URLs (the bare /en/<cat>/ slugs 404).
# These power discovery; the parser only consumes detail pages.
MODERNFIREARMS_SEED_URLS = {
    "handguns": "https://modernfirearms.net/en/handguns-semi-auto-pistols-and-revolvers/",
    "submachine-guns": "https://modernfirearms.net/en/submachine-guns-history-development-technical/",
    "military-rifles": "https://modernfirearms.net/en/military-rifles/",
    "assault-rifles": "https://modernfirearms.net/en/is-there-a-thing-such-as-an-assault-rifle/",
    "sniper-rifles": "https://modernfirearms.net/en/modern-sniper-rifles/",
    "civilian-rifles": "https://modernfirearms.net/en/civilian-rifles/",
    "shotguns": "https://modernfirearms.net/en/combat-shotguns/",
    "machine-guns": "https://modernfirearms.net/en/machine-guns/",
    "anti-tank-rifles": "https://modernfirearms.net/en/anti-tank-rifles/",
    "grenade-launchers": "https://modernfirearms.net/en/grenade-launchers/",
    "ammunition": "https://modernfirearms.net/en/ammunition/",
}

# Map modernfirearms categories → A-SAN catalog categories.
# All are "Small arms" except grenade-launchers (Rocket and missile weapons,
# since most are infantry support weapons / anti-tank launchers).
_MF_TO_ASAN = {
    "handguns": "Small arms",
    "submachine-guns": "Small arms",
    "military-rifles": "Small arms",
    "assault-rifles": "Small arms",
    "sniper-rifles": "Small arms",
    "civilian-rifles": "Small arms",
    "shotguns": "Small arms",
    "machine-guns": "Small arms",
    "anti-tank-rifles": "Small arms",
    "grenade-launchers": "Rocket and missile weapons",
    "ammunition": "Small arms",
}


def parse_modernfirearms_listing(html: str) -> list[tuple[str, str, str]]:
    """Parse a modernfirearms.net category index page.

    The index pages render a sidebar tree of every firearm in the category as
    ``<a class="name" href="https://modernfirearms.net/en/<cat>/<subcat>/<country>-<subcat>/<slug>/">Name</a>``.
    Country/group links contain ``/category/`` in the path and are skipped;
    only the model detail URLs (5+ path segments, no ``/category/``) are kept.

    Returns [(detail_url, model_name, excerpt), ...] — one per model.
    (Excerpt is empty on this site; the index does not carry card excerpts.)
    """
    if not html:
        return []
    out: list[tuple[str, str, str]] = []
    # <a class="name" href="https://modernfirearms.net/en/.../slug/">Model Name</a>
    link_re = re.compile(
        r'<a\s+class="name"\s+href="(https?://modernfirearms\.net/en/[^"]+)"[^>]*>(.*?)</a>',
        re.S | re.I)
    for m in link_re.finditer(html):
        url = html_lib.unescape(m.group(1)).strip()
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if not url or not name:
            continue
        # Skip country/group index links (they contain /category/)
        if "/category/" in url:
            continue
        # Detail pages have 5+ path segments:
        # /en/<cat>/<subcat>/<country>-<subcat>/<slug>/  -> 6 segments after the host
        path = url.split("modernfirearms.net/en/", 1)[-1].strip("/")
        if path.count("/") < 3:
            continue
        out.append((url, name, ""))
    # Dedupe by URL preserving order
    seen: set[str] = set()
    deduped: list[tuple[str, str, str]] = []
    for u, n, e in out:
        if u not in seen:
            seen.add(u)
            deduped.append((u, n, e))
    return deduped


def _td_cells(el_html: str) -> list[str]:
    """Cell texts of a <tr> row, tags stripped and entities unescaped."""
    return [
        re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", c))).strip()
        for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", el_html, re.S | re.I)
    ]


def _spec_table(body_html: str) -> list[str]:
    """Extract 'Key: Value' pairs from MF spec tables. Two page shapes:
      1. TTX: <thead>Specification|Value</thead> + <tr><td>k</td><td>v</td></tr>
      2. Bordered: >=3 rows of <td><b>Key</b></td><td>value</td>
    Returns specs in page order; skips header/no-value rows."""
    specs: list[str] = []
    seen: set[str] = set()
    for tbl_m in re.finditer(r"<table[^>]*>(.*?)</table>", body_html, re.S | re.I):
        tbl = tbl_m.group(1)
        ttx = bool(re.search(r">\s*Specification\s*<", tbl, re.I))
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I)
        parsed: list[tuple[str, str]] = []
        bold_keys = 0
        for tr in rows:
            cells = _td_cells(tr)
            raw_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
            if len(cells) < 2 or not cells[0] or not cells[1]:
                continue
            k, v = cells[0], " ".join(cells[1:])
            if k.lower() in ("specification", "value"):
                continue
            if any(re.search(r"<(b|strong)[^>]*>", rc.strip()[:20], re.I)
                   for rc in raw_cells[:1]):
                bold_keys += 1
            parsed.append((k, v))
        if not (ttx or bold_keys >= 3):
            continue
        for k, v in parsed:
            pair = f"{k}: {v}"
            if v.lower() not in ("&nbsp;", "nbsp") and pair not in seen:
                seen.add(pair)
                specs.append(pair)
        if specs:
            break
    return specs


def parse_modernfirearms(url: str, html: str, category_display: str = "") -> CatalogEntry | None:
    """Parse a modernfirearms.net detail page (e.g. /en/assault-rifles/finland-.../slug/)."""
    if not html:
        return None

    # <h1>Sako ARG, Automatkarbin 24 / AK 24 rifle (Finland)</h1> — only one h1 per page
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if not h1_m:
        t_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if not t_m:
            return None
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", t_m.group(1))).strip()
        title = re.sub(r"\s*[|\-–]\s*Modern Firearms.*$", "", title, flags=re.I).strip()
    else:
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).strip()

    if not title:
        return None

    # Country is in the trailing (Country) parens of the title, or in the URL
    # path segment <country>-<category>.
    country = ""
    paren_m = re.search(r"\(([^)]+)\)\s*$", title)
    if paren_m:
        country = paren_m.group(1).strip()
        title_clean = re.sub(r"\s*\([^)]+\)\s*$", "", title).strip()
    else:
        title_clean = title
        # Try URL: /en/assault-rifles/finland-assault-rifles/slug/
        url_m = re.search(r"/en/[^/]+/([a-z]+)-[a-z-]+/", url, re.I)
        if url_m:
            from .config import COUNTRY_FIXUPS, COUNTRIES
            cand = url_m.group(1).lower()
            if cand in COUNTRY_FIXUPS:
                country = COUNTRY_FIXUPS[cand]
            elif cand in COUNTRIES:
                country = url_m.group(1).capitalize()

    # Main content column: <div class="col-sm-9 col-lg-8"> ... </div>
    # (some templates use class="col-xs-12 col-sm-9")
    content_m = re.search(
        r'<div\s+class="[^"]*col-sm-9[^"]*"[^>]*>(.*?)</div>\s*(?:<div\s+class="[^"]*col-|<aside|</div>\s*</div>\s*<footer)',
        html, re.S | re.I)
    body_html = content_m.group(1) if content_m else html

    # Body paragraphs
    paras = re.findall(r"<p[^>]*>(.*?)</p>", body_html, re.S | re.I)
    body = " ".join(
        re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", p))).strip()
        for p in paras[:4] if p.strip()
    ).strip()
    if not body:
        body = f"Modern Firearms encyclopedia entry: {title_clean}"

    # Spec list, two shapes:
    #   1. TTX table: <thead>Specification|Value</thead> + <tr><td>k</td><td>v</td></tr>
    #   2. <p>...specifications...</p><ul><li>Key: Value</li></ul>
    specs: list[str] = _spec_table(body_html)
    if not specs:
        # Shape 3: <p><strong>Characteristics:</strong></p>
        #          <p><b>Key: </b>value<br /><b>Key2:</b> value2</p>
        char_m = re.search(
            r"(?:characteristics|specifications)[^<]*</(?:strong|em|b)>.*?<p[^>]*>(.*?)</p>",
            body_html, re.S | re.I)
        if char_m:
            block = re.sub(r"<br\s*/?>", "\n", char_m.group(1), flags=re.I)
            for line in block.split("\n"):
                t = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", line))).strip()
                m = re.match(r"^([A-Za-z][A-Za-z0-9 /(),.'-]{1,38}):\s*(.+)$", t)
                if m and m.group(2).strip():
                    specs.append(f"{m.group(1).strip()}: {m.group(2).strip()}")
    if not specs:
        # Find a heading paragraph that contains "specifications" then the following <ul>
        spec_h_m = re.search(
            r"<p[^>]*>\s*<[^>]*>\s*<strong[^>]*>[^<]*specifications[^<]*</strong>[^<]*</[^>]*>\s*</p>(.*?)</ul>",
            body_html, re.S | re.I)
        if not spec_h_m:
            # Looser: any <ul> of <li>Key: Value</li> items
            spec_h_m = re.search(r"specifications.*?<ul[^>]*>(.*?)</ul>", body_html, re.S | re.I)
        if spec_h_m:
            ul_body = spec_h_m.group(1) if "spec_h_m" in dir() else spec_h_m.group(0)
            # Get the actual <ul> contents
            ul_m = re.search(r"<ul[^>]*>(.*?)</ul>", spec_h_m.group(0), re.S | re.I)
            if ul_m:
                ul_body = ul_m.group(1)
            lis = re.findall(r"<li[^>]*>(.*?)</li>", ul_body, re.S | re.I)
            for li in lis:
                t = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", li))).strip()
                if ":" in t:
                    k, v = t.split(":", 1)
                    if k.strip() and v.strip():
                        specs.append(f"{k.strip()}: {v.strip()}")

    # Category from URL path or fallback
    if not category_display or category_display == "Uncategorized":
        cat_m = re.search(r"/en/([a-z-]+)/", url, re.I)
        if cat_m:
            mf_cat = cat_m.group(1)
            # Strip country suffix from sub-path (e.g. "finland-assault-rifles")
            mf_cat_key = mf_cat.split("-", 1)[0] if "-" in mf_cat else mf_cat
            category_display = _MF_TO_ASAN.get(mf_cat) or _MF_TO_ASAN.get(mf_cat_key, "Small arms")

    return CatalogEntry(
        designation=title_clean,
        alt_names=[],
        country=country,
        manufacturer="",  # Embedded in body prose; no structured field on this site
        category=category_display,
        description=body[:500],
        specs=specs[:20],
        sources=[SourceRef("ModernFirearms.net", url)],
        fetched_at=now_iso(),
    )
