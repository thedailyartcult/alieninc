"""Parser for seaforces.org — naval fleets, ship classes and weapon systems.

robots.txt: `User-Agent:* Disallow:` (empty = nothing disallowed) plus a flat
sitemap.txt enumerating every page (~2,800 URLs). Sections used:
  /wpnsys/{SURFACE,SUBMARINE,AIRCRAFT}  — naval weapon systems (Mk-41 VLS…)
  /usnships/…                            — US Navy ship classes + hulls
  /marint/<Country-Navy>/…               — international navies (class/hull)
Skipped by policy: /usnair/, /usmcair/ (squadron/org pages, not equipment),
/spcrep/ (special reports).

© Seaforces — fact extraction with attribution: specification blocks +
short description + exact source URL. See POLICY.md.
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.seaforces.org"

_SPEC_KWS = ("specifications", "characteristics")
_CAPABILITY_KWS = (" can ", " equipped ", " fitted ", " armed with ", " powered by ",
                   " carries ", " range of ", " speed of ", " in service",
                   " commissioned", " displacement")

# Keys we accept from packed table cells — excludes hull-number chronology
# lists ('USS Essex: (1942-69)') that otherwise win on volume.
_SPEC_KEYS = {
    "displacement", "length", "beam", "draft", "draught", "height", "speed",
    "range", "complement", "propulsion", "machinery", "armament", "aircraft",
    "sensors", "radar", "sonar", "ew", "countermeasures", "builders",
    "builder", "class", "endurance", "capacity", "troops", "payload",
    "crew", "boilers", "turbines", "shafts", "power plant", "fuel",
    "aviation", "boats", "missiles", "guns", "torpedoes", "decoys", "aegis",
    "type", "namesake", "laid down", "launched", "commissioned",
}


def _designation_from_url(url: str) -> str:
    slug = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1])
    slug = re.sub(r"\.html?$", "", slug, flags=re.I)
    return re.sub(r"[\-_]+", " ", slug).strip()


def _country_from_url(url: str, path: str) -> str:
    m = re.search(r"/marint/([A-Za-z\-]+)/", url)
    if m:
        name = m.group(1)
        name = re.sub(r"-Navy$", "", name, flags=re.I)
        return name.replace("-", " ").strip()
    if "/usnships/" in path or "/usnair/" in path:
        return "United States"
    return ""


def _extract_specs(body: str) -> list[str]:
    """Pull 'Specifications:' blocks structured as <strong>Label:</strong>
    followed by the value markup, until the next <strong>/label."""
    lower = body.lower()
    anchor = -1
    for kw in _SPEC_KWS:
        anchor = lower.find(kw)
        if anchor != -1:
            break
    if anchor == -1:
        return []
    region = body[anchor:anchor + 12000]

    def _clean(s: str) -> str:
        s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
        s = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", html_lib.unescape(s)).strip()

    specs: list[str] = []
    for seg in re.split(r"<(?:strong|b)[^>]*>", region)[1:]:
        head, sep, tail = seg.partition("</strong>")
        if not sep:
            head, sep, tail = seg.partition("</b>")
            if not sep:
                continue
        label_raw = _clean(head)
        mm = re.search(r"([A-Za-z0-9 /()\-]{2,50}?):\s*$", label_raw)
        if not mm:
            continue
        label = mm.group(1).strip()
        ll = label.lower()
        if ll.startswith(("specification", "characteristic")):
            continue
        if ll.startswith("home") or " | " in label:
            break
        value = _clean(tail)[:300]
        if label and value:
            specs.append(f"{label}: {value}")
        if len(specs) >= 24:
            break
    return specs


def _table_cell_specs(body: str) -> list[str]:
    """Second shape: spec blocks packed in ONE <td> as repeated
    '<strong>Key:</strong> value' segments separated by <br/> (Essex-class
    style). Scans every table cell; needs >=3 clean pairs to trust."""
    best: list[str] = []
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S | re.I):
        keys = re.findall(r"<(?:strong|b)[^>]*>\s*([A-Za-z][A-Za-z0-9 /()\-]{2,38}?)\s*:?\s*(?:<br\s*/?>)?\s*</(?:strong|b)>",
                          cell, re.S | re.I)
        if len(keys) < 3:
            continue
        # Split the cell on each bold key marker, pairing marker->following text
        parts = re.split(r"<(?:strong|b)[^>]*>", cell)[1:]
        found: list[str] = []
        for part in parts:
            head, sep, tail = part.partition("</strong>")
            if not sep:
                head, sep, tail = part.partition("</b>")
                if not sep:
                    continue
            label_raw = re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", head, flags=re.I)).strip()
            mm = re.match(r"([A-Za-z][A-Za-z0-9 /()\-]{2,40}?):?\s*$", label_raw)
            if not mm:
                continue
            label = mm.group(1).strip()
            if "|" in label or not tail:
                continue
            ll = label.lower()
            if not any(ll.startswith(k) or k in ll for k in _SPEC_KEYS):
                continue
            if ll.startswith(("home", "specification", "characteristic")):
                continue
            # value = text after </strong> up to the next bold block start
            stop = re.search(r"<(?:strong|b)[^>]*>", tail)
            vseg = tail[:stop.start()] if stop else tail
            v = re.sub(r"<br\s*/?>", " ", vseg, flags=re.I)
            v = re.sub(r"<[^>]+>", " ", v)
            v = re.sub(r"\s+", " ", html_lib.unescape(v)).strip(" /&;")
            if label and v and len(v) > 1 and len(v) <= 250 \
                    and v.lower() not in ("&nbsp;", "nbsp"):
                found.append(f"{label}: {v}")
        if len(found) > len(best):
            best = found
        if len(best) >= 15:
            break
    return best


def parse_seaforces(url: str, html: str) -> CatalogEntry | None:
    """Parse a seaforces.org weapon-system / ship-class page."""
    if not html:
        return None

    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
                  "", html, flags=re.S | re.I)

    designation = _designation_from_url(url)
    if not designation or len(designation) > 120:
        return None

    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.findall(r"<(?:p|td)[^>]*>(.*?)</(?:p|td)>", body,
                                      re.S | re.I)]
    paragraphs = [re.sub(r"\s+", " ",
                         html_lib.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
                  for p in paragraphs]
    paragraphs = [p for p in paragraphs if len(p) > 90
                  and " | " not in p[:80] and not p.upper().startswith("HOME")]

    # Prefer prose ("X was/is ...") over hull-list or table-of-units blocks.
    description = ""
    for p in paragraphs:
        pl = p.lower()
        if " was " in pl or " is " in pl or " are " in pl:
            description = p[:600]
            break
    if not description:
        description = next((p for p in paragraphs), "")[:600]

    specs = _extract_specs(body)
    cell_specs = _table_cell_specs(body)
    if len(cell_specs) > len(specs):
        specs = cell_specs
    elif specs:
        seen = {s.split(":", 1)[0].lower() for s in specs}
        specs.extend(s for s in cell_specs if s.split(":", 1)[0].lower() not in seen)

    if not description and not specs:
        return None  # index/hub or org-only page — no equipment data.

    path = urllib.parse.urlsplit(url).path.lower()
    country = _country_from_url(path, path)

    if "/wpnsys/" in path:
        text = f"{designation} {description}".lower()
        category = "Rocket and missile weapons" if \
            any(k in text for k in ("missile", "rocket", "torpedo", "gun")) \
            else "Naval vessels"
    else:
        category = "Naval vessels"

    return CatalogEntry(
        designation=designation,
        category=category,
        country=country,
        description=description or f"{designation} — Seaforces profile.",
        specs=specs,
        sources=[SourceRef("Seaforces", url)],
        fetched_at=now_iso(),
    )
