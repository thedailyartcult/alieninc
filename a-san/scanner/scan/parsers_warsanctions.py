"""Parser for war-sanctions.gur.gov.ua — "War & Sanctions" portal run by the
Ukrainian Defence Intelligence (GUR). Tracks the aggressor's military-industrial
complex: UAV systems, manufacturers, components-in-weapons supply chains.

robots.txt: User-agent:* Allow:/ except /office,/search,/api,/data,/subscription,
/download-controller. Cloudflare Content-Signals: search=yes, ai-train=no,
use=reference — fact extraction with attribution is permitted; raw text must NOT
be used for AI model training/fine-tuning (see POLICY.md).

Politeness: this is a Ukrainian government intelligence portal operated during an
active war — crawl with an explicit per-host delay (net.HOST_CRAWL_DELAY = 3s).
"""
from __future__ import annotations

import html as html_lib
import re

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "war-sanctions.gur.gov.ua"

# Detail URL shape: /en/uav/<numeric-id>
_UAV_ID_RE = re.compile(
    r'href="(https?://war-sanctions\.gur\.gov\.ua/en/uav/(\d+))"', re.I)

# Declared characteristics block:
#   <div class="col-12 col-lg-6 yellow">Label</div>
#   <div class="col-12 col-lg-6 text-white font-weight-bold">
#       <span class="js_visibility_target">Value</span></div>
_SPEC_RE = re.compile(
    r'<div[^>]*class="[^"]*\byellow\b[^"]*"[^>]*>\s*(.*?)\s*</div>\s*'
    r'<div[^>]*class="[^"]*\btext-white\b[^"]*"[^>]*>\s*'
    r'<span[^>]*class="[^"]*js_visibility_target[^"]*"[^>]*>(.*?)</span>',
    re.S | re.I)

# Related company cards: <div class="...profile-div..."> ... alt="NAME" ...
_COMPANY_RE = re.compile(
    r'<div[^>]*class="[^"]*profile-div[^"]*"[^>]*>.*?alt="([^"]+)"', re.S | re.I)


def parse_warsanctions_uav_listing(html: str) -> list[str]:
    """Extract unique UAV detail URLs from a /en/uav listing page."""
    if not html:
        return []
    seen: dict[str, None] = {}
    for m in _UAV_ID_RE.finditer(html):
        seen.setdefault(m.group(1), None)
    return list(seen)


def parse_warsanctions_uav(url: str, html: str) -> CatalogEntry | None:
    """Parse a war-sanctions.gur.gov.ua/en/uav/<id> detail page."""
    if not html:
        return None

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if not h1_m:
        return None
    name = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return None

    # Purpose tag: the portal exposes it as twitter:description ("FPV kamikaze",
    # "Reconnaissance", ...). Fall back to the visible chip near the H1.
    purpose = ""
    meta_m = re.search(
        r'<meta[^>]+name="twitter:description"[^>]+content="([^"]*)"', html, re.I)
    if not meta_m:
        meta_m = re.search(
            r'<meta[^>]+content="([^"]*)"[^>]+name="twitter:description"', html, re.I)
    if meta_m:
        purpose = html_lib.unescape(meta_m.group(1)).strip()

    # Specs live in the "Declared characteristics" region only — slice it out so
    # unrelated yellow label divs (Related companies etc.) don't match.
    specs_region = html
    start = html.find("Declared characteristics")
    if start != -1:
        end = len(html)
        for marker in ("Related companies", "Provide additional information"):
            i = html.find(marker, start)
            if i != -1:
                end = min(end, i)
        specs_region = html[start:end]

    specs: list[str] = []
    for label, value in _SPEC_RE.findall(specs_region):
        label = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", label))).strip()
        value = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", value))).strip()
        if label and value:
            specs.append(f"{label}: {value}")

    companies: list[str] = []
    comp_m = re.search(r"Related companies(.*?)$", html, re.S)
    if comp_m:
        for m in _COMPANY_RE.finditer(comp_m.group(1)):
            cname = html_lib.unescape(m.group(1)).strip()
            if cname and cname not in companies:
                companies.append(cname)

    description = f"Russian UAV ({purpose or 'purpose unstated'}) tracked by the " \
                  f"GUR War & Sanctions portal."
    if companies:
        description += f" Related manufacturers: {'; '.join(companies[:4])}."

    return CatalogEntry(
        designation=name,
        category="UAVs",
        country="Russia",
        manufacturer="; ".join(companies[:5]),
        description=description[:600],
        specs=specs[:20],
        sources=[SourceRef("War & Sanctions (GUR Ukraine)", url)],
        fetched_at=now_iso(),
    )
