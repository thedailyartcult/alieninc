"""
Arsenal adapter — READ-ONLY live bridge to Alien Inc's proprietary weapon
catalog (a-san). The catalog file stays the single source of truth: this
module never copies the dataset out, never transmits it anywhere, and never
logs entry contents. All access is behind Panteon authentication.

The dataset is continuously updated by the team; an mtime cache guarantees we
always reflect the latest file without re-parsing on every request.
"""
import json
import os
import threading
import time

CATALOG_PATH = os.environ.get("ALIEN_ARSENAL_CATALOG",
                              "/home/alieninc/a-san/catalog-data.json")

_lock = threading.Lock()
_cache = {
    "mtime": None,
    "loaded_at": 0.0,
    "by_category": {},     # category_key -> list[entry]
    "categories": [],
    "entry_counts": {},
    "total_entries": 0,
    "country_index": {},   # normalized country -> {category_key: [idx,...]}
}


# ------------------------------------------------------------------ normalize
_COUNTRY_FIXUPS = {
    "japan maritime self defense force": "Japan",
    "japan maritime self-defense force": "Japan",
    "royal": "United Kingdom",
    "soviet union": "Soviet Union / Russia",
    "ussr": "Soviet Union / Russia",
    "united states of america": "United States",
    "usa": "United States",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "republic of korea": "South Korea",
    "korea, south": "South Korea",
    "korea, north": "North Korea",
    "russian federation": "Russia",
    "czech republic": "Czechia",
    "united arab emirates": "UAE",
}

# Values that are clearly NOT countries (data-entry noise in some rows).
_NON_COUNTRY = {"weight", "-", "prototype", "n/a", "unknown", "various", ""}

# ISO3 codes (theater parties + frequent catalog values) -> display names.
_ISO3_NAMES = {
    "CHN": "China", "TWN": "Taiwan", "USA": "United States", "JPN": "Japan",
    "RUS": "Russia", "UKR": "Ukraine", "BLR": "Belarus", "POL": "Poland",
    "ROU": "Romania", "MDA": "Moldova", "EST": "Estonia", "LVA": "Latvia",
    "LTU": "Lithuania", "ISR": "Israel", "SYR": "Syria", "LBN": "Lebanon",
    "IRN": "Iran", "JOR": "Jordan", "IRQ": "Iraq", "PRK": "North Korea",
    "KOR": "South Korea", "SAU": "Saudi Arabia", "ARE": "UAE", "QAT": "Qatar",
    "KWT": "Kuwait", "BHR": "Bahrain", "OMN": "Oman", "MLI": "Mali",
    "BUR": "Burkina Faso", "NER": "Niger", "TCD": "Chad", "MRT": "Mauritania",
    "FRA": "France", "PER": "Peru", "BOL": "Bolivia", "ECU": "Ecuador",
    "COL": "Colombia", "VEN": "Venezuela", "CHL": "Chile", "BRA": "Brazil",
    "VNM": "Vietnam", "PHL": "Philippines", "MYS": "Malaysia", "BRN": "Brunei",
    "IDN": "Indonesia", "DEU": "Germany", "GBR": "United Kingdom",
    "ITA": "Italy", "ESP": "Spain", "TUR": "Turkey", "IND": "India",
    "PAK": "Pakistan", "EGY": "Egypt", "ZAF": "South Africa",
}


def normalize_country(raw: str) -> str | None:
    """Map messy operator/origin strings (incl. ISO3) to a canonical name."""
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in _NON_COUNTRY:
        return None
    if len(key) == 3 and key.isalpha():
        upper = key.upper()
        if upper in _ISO3_NAMES:
            return _ISO3_NAMES[upper]
    return _COUNTRY_FIXUPS.get(key, str(raw).strip())


def _parse_spec_value(text: str):
    """'Maximum Speed: 98 mph' -> ('maximum_speed', '98 mph') when parseable."""
    if ":" not in text:
        return None
    k, _, v = text.partition(":")
    k = k.strip().lower().replace(" ", "_").replace(".", "").replace("/", "_")
    v = v.strip()
    return (k, v) if k and v else None


def _index_entries(entries_by_cat: dict) -> dict:
    """Build normalized country index over all entries."""
    idx = {}
    for cat, entries in entries_by_cat.items():
        for i, e in enumerate(entries):
            c = normalize_country(e.get("country"))
            if not c:
                continue
            idx.setdefault(c.lower(), {}).setdefault(cat, []).append(i)
    return idx


def load_catalog(force: bool = False) -> dict:
    """Return cached catalog view; re-parse only when file mtime changed."""
    try:
        mtime = os.stat(CATALOG_PATH).st_mtime
    except OSError:
        return {"available": False, "error": f"catalog missing at {CATALOG_PATH}"}
    with _lock:
        fresh = (_cache["mtime"] == mtime and _cache["by_category"])
        if force or not fresh:
            with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("entries") or {}
            _cache["mtime"] = mtime
            _cache["loaded_at"] = time.time()
            _cache["by_category"] = entries
            _cache["categories"] = data.get("category_keys") or []
            _cache["entry_counts"] = data.get("entry_counts") or {}
            _cache["total_entries"] = data.get("total_entries") or sum(
                len(v) for v in entries.values())
            _cache["country_index"] = _index_entries(entries)
    view = dict(_cache)
    view["available"] = True
    view.pop("_lock", None)
    return view


# ------------------------------------------------------------------- queries
def capability_counts(country_raw: str) -> dict:
    """Real equipment counts per category for one nation."""
    cat_view = load_catalog()
    if not cat_view.get("available"):
        return cat_view
    country = normalize_country(country_raw)
    if not country:
        return {"available": True, "country": None, "counts": {}}
    buckets = cat_view["country_index"].get(country.lower()) or {}
    counts = {cat: len(ix) for cat, ix in sorted(buckets.items())}
    return {"available": True, "country": country, "counts": counts,
            "total": sum(counts.values())}


def query_entries(country: str | None = None, category: str | None = None,
                  q: str | None = None, limit: int = 50, offset: int = 0,
                  include_description: bool = True) -> dict:
    """
    Live query over the proprietary catalog.
    Filters combine with AND; q matches designation/alt_names/description/
    manufacturer/specs substring. Returns metadata + entries (never logged).
    """
    view = load_catalog()
    if not view.get("available"):
        return view
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    norm_country = normalize_country(country) if country else None
    cats = [category] if category else view["categories"]
    hits = []
    matched = 0  # total matches seen (incl. skipped-by-offset)
    qlow = (q or "").lower()

    for cat in cats:
        entries = view["by_category"].get(cat, [])
        bucket = view["country_index"].get((norm_country or "").lower())
        if norm_country:
            indices = set((bucket or {}).get(cat, []))
            iterable = ((i, entries[i]) for i in sorted(indices))
        else:
            iterable = enumerate(entries)
        for i, e in iterable:
            if qlow:
                hay = " ".join([e.get("designation") or "",
                                " ".join(e.get("alt_names") or []),
                                e.get("description") or "",
                                e.get("manufacturer") or "",
                                " ".join(e.get("specs") or [])]).lower()
                if qlow not in hay:
                    continue
            matched += 1
            if matched <= offset or len(hits) >= limit:
                continue
            specs = {}
            unparsed_specs = []
            for s in (e.get("specs") or []):
                parsed = _parse_spec_value(s)
                if parsed:
                    specs[parsed[0]] = parsed[1]
                elif s.strip():
                    unparsed_specs.append(s.strip())
            hits.append({
                "category": cat,
                "designation": e.get("designation"),
                "alt_names": e.get("alt_names") or [],
                "country": normalize_country(e.get("country")) or e.get("country"),
                "manufacturer": e.get("manufacturer") or None,
                **({"description": e.get("description")} if include_description else {}),
                "specs_parsed": specs,
                "specs_extra": unparsed_specs[:8],
                "sources": [{"label": s.get("label"), "url": s.get("url")}
                            for s in (e.get("sources") or [])],
                "fetched_at": e.get("fetched_at"),
            })

    return {
        "available": True,
        "query": {"country": norm_country, "category": category, "q": q},
        "total_matched_estimate": matched,
        "offset": offset, "limit": limit,
        "entries": hits,
        "categories": view["categories"],
        "catalog_totals": {"entries": view["total_entries"],
                           "categories": len(view["categories"])},
    }


def curated_flagships(country_raw: str, per_category: int = 2) -> list[dict]:
    """
    Deterministically pick flagship systems per category for one nation
    (most recently fetched entries first) for curated ontology linking.
    """
    view = load_catalog()
    if not view.get("available"):
        return []
    norm_country = normalize_country(country_raw)
    if not norm_country:
        return []
    bucket = view["country_index"].get(norm_country.lower()) or {}
    flagships = []
    for cat, indices in sorted(bucket.items()):
        entries = view["by_category"].get(cat, [])
        ranked = sorted(indices, key=lambda i: entries[i].get("fetched_at") or "",
                        reverse=True)[:per_category]
        for i in ranked:
            e = entries[i]
            specs = [s for s in (e.get("specs") or []) if s.strip()]
            flagships.append({
                "pk": f"arsenal:{cat}:{(e.get('designation') or '').strip().lower()[:80]}",
                "category": cat,
                "designation": e.get("designation"),
                "country": norm_country,
                "manufacturer": e.get("manufacturer") or None,
                "description": (e.get("description") or "")[:400],
                "alt_names": e.get("alt_names") or [],
                "top_specs": specs[:6],
                "sources_count": len(e.get("sources") or []),
                "fetched_at": e.get("fetched_at"),
            })
    return flagships
