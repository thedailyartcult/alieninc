"""Target loader — reads targets.json and profile files."""

import json
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent
TARGETS_DIR = ENGINE_DIR / "targets"
PROFILES_DIR = TARGETS_DIR / "profiles"
BASE_DIR = ENGINE_DIR.parent.parent
_cache = {}


def load_targets():
    """Load targets from targets.json."""
    if "targets" in _cache:
        return _cache["targets"]
    path = TARGETS_DIR / "targets.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    targets = []
    for t in data.get("targets", []):
        resolved = BASE_DIR / t.get("path", "/").strip("/")
        targets.append({
            "id": t["id"], "name": t["name"], "type": t.get("type", "subsidiary"),
            "path": t.get("path", "/"), "base_path": resolved,
            "exclude": t.get("exclude", []), "audits": t.get("audits", []),
            "url": t.get("url", "https://alieninc.tech/"),
        })
    _cache["targets"] = targets
    return targets


def load_profile(profile_name):
    """Load profile by name. Falls back to all audit IDs if not found."""
    if f"profile:{profile_name}" in _cache:
        return _cache[f"profile:{profile_name}"]
    path = PROFILES_DIR / f"{profile_name}.json"
    if not path.exists():
        from scanners.audit_loader import list_audit_ids
        return list_audit_ids()
    with open(path) as f:
        data = json.load(f)
    result = data.get("audit_ids", [])
    _cache[f"profile:{profile_name}"] = result
    return result


def list_profiles():
    """List available scan profiles."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(f.stem for f in PROFILES_DIR.glob("*.json"))
