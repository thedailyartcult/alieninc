"""Build the Panteon MIL-contacts airframe index from the a-san catalog.

Reads data/aircraft.json (exported by export_web) and derives ADS-B-style
type keys ("f16", "su27", "kc135", "typhoon") from designation + alt_names
tokens, then writes the compact index consumed by admin.html's MIL contacts
rail via /static/a-san-aircraft-index.json.

Run automatically as part of `python -m scan build-web`; also standalone:
    python3 -m scan.aircraft_index [output_path]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUT = Path("/home/alieninc/panteon/a-san-aircraft-index.json")

# Generic words that never make useful type keys.
_STOP_TOKENS = {
    "aircraft", "airplane", "plane", "helicopter", "helos", "class", "type",
    "block", "variant", "series", "mark", "mki", "advanced", "light",
    "medium", "heavy", "combat", "attack", "trainer", "transport", "utility",
    "reconnaissance", "surveillance", "patrol", "maritime", "naval", "navy",
    "force", "air", "joint", "strike", "fighter", "bomber", "cargo",
    "tanker", "airlift", "awacs", "early", "warning", "unmanned", "aerial",
    "vehicle", "drone", "uav", "uas", "system", "program", "project",
    "experimental", "prototype", "production", "improved", "upgraded",
    "modernized", "super", "superhornet", "thunderbolt", "warthog", "eagle",
    "falcon", "tomcat", "phantom", "skyhawk", "tigershark", "raptor",
    "lightning", "lightningii", "hornet", "flanker", "fulcrum", "foxhound",
    "fishbed", "viking", "sentinel", "heron", "hermes", "wasp", "wolverine",
    "stratotanker", "stratofortress", "poseidon", "sentry", "shadow",
    "reaper", "predator", "global", "talon", "hurricane", "spitfire",
    "mustang", "liberator", "fortress", "invader", "havoc", "marauder",
    "apache", "guardian", "cobra", "comanche", "kiowa", "blackhawk",
    "seahawk", "chinook", "huey", "venom", "viper", "demons",
}

_ALNUM = re.compile(r"[^a-z0-9]")
_TOKEN_SPLIT = re.compile(r"[\s()\[\]:;'\"\u2019,|]+")


def _candidate_keys(text: str) -> list[str]:
    """Extract plausible ADS-B-style type keys from one name string."""
    if not text:
        return []
    # "F/A-18" -> "FA-18" so the slash doesn't orphan the prefix
    keys = []
    for tok in _TOKEN_SPLIT.split(text.replace("/", "")):
        t = tok.strip()
        if not t or len(t) > 24:
            continue
        k = _ALNUM.sub("", t.lower())
        if not k or len(k) < 2 or len(k) > 8 or k in _STOP_TOKENS:
            continue
        has_digit = any(ch.isdigit() for ch in k)
        # keep: digit-bearing designations (f16, su27, c130, dh8a), OR
        # short alpha slugs likely to be name/ICAO-style codes (typhoon)
        if (has_digit and not k.isdigit()) or (k.isalpha() and len(k) >= 5):
            if k not in keys:
                keys.append(k)
            # letter-stripped variant so "ah64e"/"kc135r" resolve base types
            stripped = k.rstrip("abcdefghijklmnopqrstuvwxyz")
            if stripped != k and len(stripped) >= 2 and any(
                    ch.isdigit() for ch in stripped) \
                    and stripped not in keys:
                keys.append(stripped)
    # joined form: "Falcon 900" -> f900, "Falcon 7X" -> f7x ("Dash 8" -> d8)
    toks = [_ALNUM.sub("", t.lower())
            for t in _TOKEN_SPLIT.split(text.replace("/", "")) if t.strip()]
    for a, b in zip(toks, toks[1:]):
        if a.isalpha() and b and b[0].isdigit():
            j = (a[0] + b)[:8]
            if len(j) >= 2 and j not in keys:
                keys.append(j)
    return keys


# ICAO type codes that cannot be derived from the catalog designation text
# (bizjets / turboprops tracked on ADS-B military-surveillance feeds).
_ICAO_ALIASES = {
    "dhc8": ["dh8a", "dh8b", "dh8c", "dh8d", "dash8"],
    "f7x": ["fa7x"],   # Dassault Falcon 7X
}


def _apply_icao_aliases(types: dict) -> None:
    for base, aliases in _ICAO_ALIASES.items():
        rec = types.get(base)
        if not rec:
            continue
        for alias in aliases:
            types.setdefault(alias, rec)


def build_index(catalog_aircraft_path: Path) -> dict:
    data = json.loads(Path(catalog_aircraft_path).read_text(encoding="utf-8"))
    entries = next(v for v in data.values() if isinstance(v, list))
    types: dict[str, dict] = {}
    for e in entries:
        names = [e.get("designation") or ""] + [
            str(a) for a in (e.get("alt_names") or [])]
        rec = {"d": (e.get("designation") or "").strip(),
               "c": (e.get("country") or "").strip(),
               "m": (e.get("manufacturer") or "").strip()}
        for name in names:
            for k in _candidate_keys(name):
                types.setdefault(k, rec)
    _apply_icao_aliases(types)
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")
                     .replace("+00:00", "Z"),
        "source": "a-san/data/aircraft.json",
        "count": len(types),
        "types": types,
    }


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    here = Path(__file__).resolve().parent
    idx = build_index(here.parent.parent / "data" / "aircraft.json")
    out.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"wrote {idx['count']} type keys -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
