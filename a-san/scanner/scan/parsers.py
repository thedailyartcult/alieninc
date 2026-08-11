"""Source-specific parsing: page HTML -> CatalogEntry (or patent record).

Only fields printed on the page are captured. No inference, no filling-in.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from .config import category_key
from .models import CatalogEntry, SourceRef, now_iso
from .parse_html import parse_html, parse_google_patents

ARMYREC_BASE = "https://www.armyrecognition.com"

# Ordering hints so the important public specs surface first.
_SPEC_ORDER = ["type", "country users", "designer country", "weight", "length", "wingspan",
               "height", "dimensions", "engine", "speed", "range", "endurance", "crew",
               "armament", "guidance", "warhead", "accuracy", "rate of fire", "caliber",
               "propulsion", "launch weight", "magazine", "payload", "max takeoff"]


_NOISE_LABELS = {"description", "technical data", "specifications", "details",
                 "pictures", "video", "back to top", "see also", "images",
                 "gallery", "visit army recognition", "search"}


def _prefer_specs(specs: list[tuple[str, str]]) -> list[str]:
    def rank(spec):
        label = spec[0].lower()
        for i, kw in enumerate(_SPEC_ORDER):
            if kw in label:
                return i
        return len(_SPEC_ORDER) + 1
    ordered = sorted(specs, key=rank)
    out = []
    seen = set()
    for label, value in ordered:
        l = label.lower()
        if l in _NOISE_LABELS:
            continue
        value = value[:400]
        line = f"{label}: {value}"
        key = l
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def parse_armyrecognition(url: str, html: str, category_display: str) -> CatalogEntry | None:
    d = parse_html(html)
    title = d["title"]
    if not title:
        return None
    title = title.split(" | ")[0].strip()
    designation = title
    specs = _prefer_specs(d["specs"])

    # country / manufacturer from the spec labels when present
    country, manufacturer = "", ""
    for label, value in d["specs"]:
        l = label.lower()
        if l in ("country users", "country of origin") and not country:
            country = value
        elif "manufacturer" in l and not manufacturer:
            manufacturer = value

    desc = d["description"] or ("Public technical profile of %s." % designation)
    desc = _strip_lead_date(desc)
    desc = re.sub(r"\s+", " ", desc).strip()[:600]

    entry = CatalogEntry(
        designation=designation,
        category=category_display,
        description=desc,
        country=country,
        manufacturer=manufacturer,
        specs=specs,
        sources=[SourceRef("Army Recognition product page", url)],
        fetched_at=now_iso(),
    )
    return entry


# Leading "March 30, 2026" / "26 Apr, 2026 - 18:42" junk before the real text.
_DATE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})"
    r"\s*[-–—–:.]*\s*", re.I)


def _strip_lead_date(text: str) -> str:
    return _DATE_PREFIX_RE.sub("", text, count=1) or text


# ---------- Google Patents ----------
def _patent_designation(d: dict, system_designation: str = "") -> str:
    """Human-readable designation: the patent's title, stripped of the
    'USxxxxx - ' prefix and ' - Google Patents' suffix. Falls back to the
    publication number, then to system_designation, then a placeholder."""
    title = (d.get("title") or "").strip()
    if title:
        title = re.sub(r"\s*-\s*Google Patents\s*$", "", title, flags=re.I)
        title = re.sub(r"^[-–]\s*", "", title)
        if " - " in title:
            title = title.split(" - ", 1)[1]
        if title:
            return title
    return system_designation or (d.get("publication") or "Patent record")


def parse_patent(url: str, html: str, category_display: str, system_designation: str = "",
                 source_label: str = "Google Patents record") -> CatalogEntry:
    d = parse_google_patents(html)
    pub = d.get("publication") or (
        url.rsplit("/", 2)[1] if "/patent/" in url else "")
    designation = _patent_designation(d, system_designation)
    specs = []
    if d.get("publication"):
        specs.append(f"Publication number: {d['publication']}")
    if d.get("abstract"):
        specs.append(f"Abstract: {d['abstract'][:400]}")
    return CatalogEntry(
        designation=designation,
        category=category_display,
        description=(d.get("abstract") or f"Public patent record {pub}.")[:600],
        specs=specs,
        sources=[SourceRef(source_label, url)],
        fetched_at=now_iso(),
    )


# ---------- Espacenet Open Patent Services (official, needs credentials) ----------
class EspacenetOPS:
    """Minimal OPS client. Requires EPO OPS developer credentials in env
    (ESPACENET_OPS_KEY / ESPACENET_OPS_SECRET). Free to register at
    developer.epo.org. This is the sanctioned, robots-compliant path for
    worldwide.espacenet.com (the web UI blocks autonomous fetches)."""

    TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
    SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"

    def __init__(self, key: str, secret: str):
        self.key, self.secret = key, secret
        self._token = None

    @property
    def available(self) -> bool:
        return bool(self.key and self.secret)

    def _get_token(self) -> str:
        if self._token:
            return self._token
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(self.TOKEN_URL, data=body, method="POST")
        req.add_header("Authorization", "Basic " +
                       __import__("base64").b64encode(f"{self.key}:{self.secret}".encode()).decode())
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read())["access_token"]
        self._token = tok
        return tok

    def search(self, query: str, start: int = 0, range_: int = 25) -> list[dict]:
        if not self.available:
            return []
        token = self._get_token()
        q = urllib.parse.urlencode({"q": query, "Range": f"{start}-{start + range_ - 1}"})
        req = urllib.request.Request(f"{self.SEARCH_URL}?{q}")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        hits = []
        for doc in data.get("ops:world-patent-data", {}).get("ops:biblio-search-result", {}).get(
                "ops:search-result", {}).get("ops:publication-reference", []):
            doc_num = doc.get("ops:document-id", [{}])[0].get("ops:doc-number")
            hits.append({"publication": doc_num})
        return hits


# ---------- USPTO (official PatentsView / PEDS are the sanctioned path) ----------
def uspto_help() -> str:
    return ("USPTO product pages require a browser/JS session. Official programmatic "
            "paths: PatentsView API (https://search.patentsview.org) and the Public "
            "Patent Application Information Retrieval (PAIR/PEDS) API — both robots-"
            "compliant and key-free. Use ppubs.uspto.gov manually for the curated set.")


# ---------- Janes (licensed research desk) ----------
def janes_import_csv(path: str) -> list[dict]:
    """Import Janes records provided by the licensed research desk as CSV.
    Expected columns: designation, alt_names, country, manufacturer, category,
    description, specs, source_url, notes. This keeps Janes data out of the
    automated crawler and under the paid licence."""
    import csv
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows
