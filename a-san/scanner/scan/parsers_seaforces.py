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
    for p in paragraphs:
        if description and p[:80] == description[:80]:
            continue
        pl = p.lower()
        if any(v in pl for v in _CAPABILITY_KWS) and len(specs) < 10:
            specs.append(p[:320])

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
