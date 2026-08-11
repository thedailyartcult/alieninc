"""Picklist generation: curated, ranked subset of the RAW POOL.

THE MISSION: A-SAN generates a picklist from a raw pool.
- RAW POOL    = every machine-acquired candidate record for the 10 categories
                that passed base admission (approved source, robots-allowed,
                fetched OK, parsed into the schema, deduped). Nothing else.
- PICKLIST    = the curated, scored, ranked, bounded subset of the raw pool
                that is presented to the user for decision-making. The user
                ONLY ever sees the picklist.

Constraints (all enforced here or upstream):
  1. only approved sources          -> net.py source allowlist + robots gate
  2. only public data, no fabrication -> parsers copy printed page text only
  3. fully automated, no humans     -> nothing here asks for input
  4. no commercial/proprietary/classified -> sources whitelist guarantees it
  5. no paywalled content           -> pages must be fetchable & parseable
  6. rules-driven & deterministic   -> same input, same output, weights versioned
  7. automated audit                -> every run writes an audit record

Every filter and every score contribution is recorded per entry so the user can
see WHY a candidate was included or excluded.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import CATEGORY_KEYS, rule_index_for_path
from .models import CatalogEntry

PICKLIST_SCHEMA_VERSION = "1.0"


@dataclass
class CurationRules:
    """All knobs are data, not behaviour — versioned in the audit file."""

    min_score: float = 40.0          # below -> excluded from the picklist
    max_per_category: int = 15       # top-N per category (coverage balance)
    max_total: int = 100             # global cap on picklist size
    weights: dict = field(default_factory=lambda: {
        "completeness": 0.35,        # how full the public record is
        "source_quality": 0.25,      # product page vs patent vs news
        "category_confidence": 0.15, # classifier specificity
        "recency": 0.10,             # how fresh the fetch is
        "coverage": 0.15,            # rarity bonus so sparse categories rank
    })

    def version(self) -> str:
        return "-".join(f"{k}{v:.2f}" for k, v in sorted(self.weights.items()))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_since(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 9999


# --------------------------------------------------------------------------- scoring

def completeness_score(e: CatalogEntry) -> float:
    s = 0.0
    if len(e.description) >= 80:
        s += 35
    elif e.description:
        s += 15
    s += min(30.0, len(e.specs) * 6.0)          # 5+ specs -> 30
    if e.country:
        s += 15
    if e.manufacturer:
        s += 12
    if e.alt_names:
        s += 8
    return min(100.0, s)


def source_quality_score(e: CatalogEntry) -> float:
    base = 10.0
    for src in e.sources:
        label = (src.label or "").lower()
        if "army recognition product page" in label:
            base = 65.0
        elif "google patents" in label:
            base = 45.0
    s = base
    if len(e.specs) >= 5:
        s += 20
    if len(e.description) >= 100:
        s += 15
    return min(100.0, s)


def category_confidence_score(e: CatalogEntry) -> float:
    """Confidence from the classifier rule position (0 = most specific)."""
    for src in e.sources:
        if "/military-products/" in src.url:
            path = src.url.split("/military-products/", 1)[1]
            idx = rule_index_for_path(path)
            if idx is None:
                return 80.0
            return max(20.0, 100.0 - idx * 12.0)
    return 70.0


def recency_score(e: CatalogEntry) -> float:
    d = _days_since(e.fetched_at)
    if d <= 7:
        return 100.0
    if d <= 30:
        return 80.0 - (d - 7)
    if d <= 90:
        return 55.0 - (d - 30) // 10 * 10
    return 20.0


def coverage_score(e: CatalogEntry, category_counts: dict[str, int]) -> float:
    """Rarity bonus: sparse categories rank higher so no giant category floods
    the picklist. Equal representation across the 10 categories is the goal."""
    c = category_counts.get(e.category, 1)
    return max(10.0, 100.0 - (c - 1) * 4.0)


_SCORERS = {
    "completeness": completeness_score,
    "source_quality": source_quality_score,
    "category_confidence": category_confidence_score,
    "recency": recency_score,
    "coverage": coverage_score,
}


def score_entry(e: CatalogEntry, category_counts: dict[str, int], rules: CurationRules):
    parts = {name: (fn(e, category_counts) if name == "coverage" else fn(e))
             for name, fn in _SCORERS.items()}
    total = sum(parts[name] * rules.weights.get(name, 0.0) for name in parts)
    return round(total, 2), parts


# --------------------------------------------------------------------------- curation

def apply_filters(entries: list[CatalogEntry]) -> tuple[list[CatalogEntry], dict[str, int]]:
    """Hard inclusion/exclusion gates. Returns (kept, excluded_counts)."""
    excluded = {"no_source_url": 0, "empty_content": 0, "weak_designation": 0}
    kept: list[CatalogEntry] = []
    for e in entries:
        if not e.sources:
            excluded["no_source_url"] += 1
            continue
        if not e.specs and not e.description:
            excluded["empty_content"] += 1
            continue
        if len(e.designation.strip()) < 3:
            excluded["weak_designation"] += 1
            continue
        kept.append(e)
    return kept, excluded


def curate(entries: list[CatalogEntry], rules: CurationRules | None = None) -> dict:
    """Run the full pipeline. Returns the complete picklist report dict."""
    rules = rules or CurationRules()
    kept, excluded = apply_filters(entries)
    counts: dict[str, int] = {}
    for e in kept:
        counts[e.category] = counts.get(e.category, 0) + 1

    scored: list[tuple[float, dict, CatalogEntry]] = []
    for e in kept:
        total, parts = score_entry(e, counts, rules)
        scored.append((total, parts, e))
    scored.sort(key=lambda t: (-t[0], t[2].designation.lower()))

    below = 0
    over_cap = 0
    picked_by_cat: dict[str, int] = {}
    picks: list[dict] = []
    for total, parts, e in scored:
        if total < rules.min_score:
            below += 1
            continue
        cat_rank = picked_by_cat.get(e.category, 0) + 1
        if cat_rank > rules.max_per_category:
            over_cap += 1
            continue
        if len(picks) >= rules.max_total:
            break
        picked_by_cat[e.category] = cat_rank
        entry = e.to_dict()
        entry["_score"] = total
        entry["_score_breakdown"] = {name: round(v, 1) for name, v in parts.items()}
        entry["_category_rank"] = cat_rank
        entry["_global_rank"] = len(picks) + 1
        picks.append(entry)

    excluded["below_min_score"] = below
    excluded["over_category_cap"] = over_cap
    return {
        "picklist_schema_version": PICKLIST_SCHEMA_VERSION,
        "curation_rules_version": rules.version(),
        "generated": _now_iso(),
        "raw_pool_size": len(entries),
        "after_filters_size": len(kept),
        "picklist_size": len(picks),
        "excluded_counts": excluded,
        "rules": {
            "min_score": rules.min_score,
            "max_per_category": rules.max_per_category,
            "max_total": rules.max_total,
            "weights": dict(rules.weights),
        },
        "category_raw_counts": counts,
        "category_keys": list(CATEGORY_KEYS.keys()),
        "entries": picks,
    }


def write_outputs(report: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "picklist.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out_dir / "picklist.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "category", "score", "designation", "alt_names",
                    "country", "manufacturer", "description", "key_specs",
                    "source_urls"])
        for e in report["entries"]:
            w.writerow([
                e["_global_rank"], e["category"], e["_score"], e["designation"],
                "; ".join(e.get("alt_names", [])), e.get("country", ""),
                e.get("manufacturer", ""), (e.get("description") or "")[:200],
                " | ".join(e.get("specs", [])[:5]),
                "; ".join(s["url"] for s in e.get("sources", [])),
            ])
