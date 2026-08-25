"""Parser for naval-encyclopedia.com — warship reference encyclopedia.

robots.txt: User-agent:* Allow:/ with Cloudflare Content-Signals
`search=yes, ai-train=no, use=reference` — fact extraction with attribution
permitted (same compliant class as war-sanctions.gur.gov.ua /
globalsecurity.org); AI-training bots are blocked, our UA is not. No
crawl-delay. Content licence © naval encyclopedia.

Page structure (.php pages):
  <title>Majestic class aircraft carriers – naval encyclopedia</title>
  <h1>Majestic class aircraft carriers</h1>
  one specifications table: <tr><td>Displacement</td><td>14,000t ...</td></tr>
  era/country from the URL path: /cold-war/uk/<slug>.php

Sections crawled: ww1, ww2, cold-war, industrial-era, modern. Battles,
civilian vessels, naval-aviation and tech pages are skipped by the
discovery path filter.
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse

from .models import CatalogEntry, SourceRef, now_iso

_HOST = "www.naval-encyclopedia.com"

# Second path segment -> country display name. Era sections without a single
# country (industrial-era decade fleet pages) map to "".
NE_COUNTRY = {
    "us": "USA", "uk": "UK", "germany": "Germany", "japan": "Japan",
    "italy": "Italy", "france": "France", "russia": "Russia",
    "ussr": "Russia/USSR", "china": "China", "spain": "Spain",
    "sweden": "Sweden", "chile": "Chile", "austria-hungary": "Austria-Hungary",
    "ottoman-fleet": "Ottoman Empire", "brazil": "Brazil",
    "argentina": "Argentina", "norway": "Norway", "netherlands": "Netherlands",
    "denmark": "Denmark", "peru": "Peru", "portugal": "Portugal",
    "romania": "Romania", "greece": "Greece", "australia": "Australia",
    "canada": "Canada", "poland": "Poland", "turkey": "Turkey",
    "finland": "Finland", "yugoslavia": "Yugoslavia", "thailand": "Thailand",
    "india": "India", "bundesmarine": "Germany", "american-civil-war": "USA",
    "secession-war": "USA", "idf": "Israel", "rnzn": "New Zealand",
    "north-korea": "North Korea", "iran": "Iran", "indonesia": "Indonesia",
    "colombia": "Colombia", "belgium": "Belgium", "south-africa": "South Africa",
}

_NE_ERAS = ("/ww1/", "/ww2/", "/cold-war/", "/industrial-era/", "/modern/")

# Slug patterns of fleet-topic / doctrine pages that are not individual
# vessels or classes (e.g. 'french-navy-1860', 'amphibious-operations').
NE_TOPIC_SLUG_RE = re.compile(
    r"(-operations(-|$)|-navy-\d{4}($|\.|-)|^navy-in-|-doctrine(-|$)"
    r"|-history(-|$)|^-fleets?)")


def is_naval_encyclopedia_ship_url(url: str) -> bool:
    """True for era/country/<slug>.php article pages worth crawling."""
    parts = urllib.parse.urlsplit(url)
    if parts.netloc not in (_HOST, "naval-encyclopedia.com"):
        return False
    m = re.match(r"^/(ww1|ww2|cold-war|industrial-era|modern)/([^/]+)/([^/]+)\.php$",
                 parts.path.lower())
    return bool(m)


def is_naval_encyclopedia_topic_page(url: str) -> bool:
    """True for fleet-overview/doctrine pages (not platforms) — excluded
    from the catalog by the post-crawl cleanup."""
    path = urllib.parse.urlsplit(url).path.lower()
    slug = path.rsplit("/", 1)[-1].replace(".php", "")
    return bool(NE_TOPIC_SLUG_RE.search(slug))


def parse_naval_encyclopedia(url: str, html: str,
                             category_display: str = "Naval vessels") \
        -> CatalogEntry | None:
    """Parse a naval-encyclopedia.com warship page."""
    if not html:
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not title_m:
        return None
    title = html_lib.unescape(title_m.group(1)).strip()
    name = re.split(r"\s*[–—-]\s*naval\s+encyclopedia\s*$", title,
                    flags=re.I)[0].strip()
    if not name or len(name) > 120:
        return None

    # Designation: trust the <title> (stable); use H1 only as fallback and
    # never accept the site-name header as a designation.
    h1s = []
    if not name or name.lower() == "naval encyclopedia":
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html[html.find("<body"):],
                         re.S | re.I)
        for h in h1s:
            cand = re.sub(r"\s+", " ",
                          html_lib.unescape(re.sub(r"<[^>]+>", "", h))).strip()
            if cand and len(cand) <= 120 \
                    and cand.lower() != "naval encyclopedia":
                name = cand
                break
    if not name or len(name) > 120 or name.lower() == "naval encyclopedia":
        return None

    # Country from the URL: /<era>/<country>/<slug>.php
    country = ""
    m = re.match(r"^/(?:ww1|ww2|cold-war|industrial-era|modern)/([^/]+)/",
                 urllib.parse.urlsplit(url).path.lower())
    if m:
        country = NE_COUNTRY.get(m.group(1), "")

    # Spec pairs from the specifications table (first cell = label).
    specs: list[tuple[str, str]] = []
    body = html[html.find("<body"):]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body,
                  flags=re.S)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S | re.I):
        cells = [re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<\s*br\s*/?\s*>", "; ", c, flags=re.I)))
            .strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr,
                                         re.S | re.I)]
        cells = [re.sub(r"<[^>]+>", "", c).strip(" ;") for c in cells]
        if len(cells) >= 2 and cells[0] and cells[1] \
                and len(cells[0]) < 40 and len(cells[1]) < 300 \
                and "specification" not in cells[0].lower():
            specs.append((cells[0], " ".join(cells[1:]) if len(cells) == 2
                          else cells[1]))

    # Description: first substantial prose paragraphs.
    desc_paras: list[str] = []
    text_m = re.search(r"<h1[^>]*>.*?</h1>(.*)", body, re.S | re.I)
    scan_zone = text_m.group(1) if text_m else body
    for p in re.findall(r"<p[^>]*>(.*?)</p>", scan_zone[:60000], re.S | re.I):
        t = re.sub(r"\s+", " ", html_lib.unescape(
            re.sub(r"<[^>]+>", "", p))).strip()
        if len(t) > 100 and not re.match(
                r"(naval encyclopedia|copyright|please|share|follow)", t, re.I):
            desc_paras.append(t)
        if len(desc_paras) >= 2:
            break
    desc = " ".join(desc_paras)[:600]
    if not desc:
        desc = f"{name} — warship analysis from naval encyclopedia."

    return CatalogEntry(
        designation=name,
        alt_names=[],
        country=country,
        manufacturer="",
        category=category_display,
        description=desc,
        specs=[f"{k}: {v}" for k, v in specs[:20]],
        sources=[SourceRef("Naval Encyclopedia", url)],
        fetched_at=now_iso(),
    )
