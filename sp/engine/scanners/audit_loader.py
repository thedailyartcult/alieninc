"""Audit file loader — reads .json audit files from the audits/ directory, validates schema, and caches for fast access."""

import json
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent
AUDITS_DIR = ENGINE_DIR / "audits"
_cache = {}


def list_audit_ids():
    """Return list of available audit file IDs (filename without .json)."""
    if not AUDITS_DIR.exists():
        return []
    return sorted(f.stem for f in AUDITS_DIR.glob("*.json") if not f.name.startswith("_"))


def load_audit(audit_id):
    """Load a single audit file by ID. Uses in-memory cache."""
    if audit_id in _cache:
        return _cache[audit_id]

    path = AUDITS_DIR / f"{audit_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Audit file not found: {path}")

    with open(path) as f:
        audit = json.load(f)

    _validate_audit(audit, audit_id)
    _cache[audit_id] = audit
    return audit


def load_audits(audit_ids):
    """Load multiple audit files. Returns dict {audit_id: audit}. Skips missing files."""
    result = {}
    for aid in audit_ids:
        try:
            result[aid] = load_audit(aid)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"  [warn] Failed to load audit '{aid}': {e}")
    return result


def get_all_items(audit_ids):
    """Flatten all items from multiple audit files into a single list with audit metadata.
    Skips INFO items (non-auditable checks) and http_live items (handled by WAT runner)."""
    items = []
    for aid in audit_ids:
        try:
            audit = load_audit(aid)
            framework = audit.get("framework", {})
            for group in audit.get("group_policies", []):
                for item in group.get("items", []):
                    # Skip INFO items (no executable check)
                    if item.get("type") == "INFO":
                        continue
                    # Skip http_live items (WAT runner handles these)
                    if item.get("assessability") == "http_live":
                        continue
                    # Skip PARENT_BENCHMARK items (reporting layer — cross-referenced from DB)
                    if item.get("type") == "PARENT_BENCHMARK":
                        continue
                    items.append({
                        **item,
                        "_audit_id": aid,
                        "_audit_name": audit.get("name", aid),
                        "_framework_id": framework.get("id", aid),
                        "_framework_name": framework.get("name", audit.get("name", "")),
                        "_framework_weight": framework.get("weight", 0.2),
                        "_group": group.get("name", ""),
                    })
        except Exception as e:
            print(f"  [warn] Skipping audit '{aid}': {e}")
    return items


def get_framework_map(audit_ids):
    """Build a framework_id → metadata map from loaded audit files."""
    frameworks = {}
    for aid in audit_ids:
        try:
            audit = load_audit(aid)
            fw = audit.get("framework", {})
            fid = fw.get("id", aid)
            if fid not in frameworks:
                frameworks[fid] = {
                    "id": fid,
                    "name": fw.get("name", audit.get("name", aid)),
                    "weight": fw.get("weight", 0.2),
                    "color": fw.get("color", "#888"),
                    "audit_ids": [],
                }
            frameworks[fid]["audit_ids"].append(aid)
        except Exception:
            pass
    return frameworks


def compute_framework_scores(results):
    """Given a list of check results (each with _framework_id), compute per-framework pass/fail."""
    totals = {}
    for r in results:
        fid = r.get("_framework_id", "unknown")
        if fid not in totals:
            totals[fid] = {"passed": 0, "failed": 0, "total": 0}
        totals[fid]["total"] += 1
        if r.get("status") == "pass":
            totals[fid]["passed"] += 1
        else:
            totals[fid]["failed"] += 1

    fw_map = {}
    for fid, data in totals.items():
        total = data["total"]
        pct = int((data["passed"] / total * 100)) if total > 0 else 0
        fw_map[fid] = {"passed": data["passed"], "failed": data["failed"], "total": total, "score": pct}
    return fw_map


def compute_weighted_security_score(framework_scores, fw_map=None):
    """Weighted average of framework scores."""
    if not framework_scores:
        return 0
    if fw_map is None:
        fw_map = {}
    weighted = 0
    total_weight = 0
    for fid, data in framework_scores.items():
        w = fw_map.get(fid, {}).get("weight", 0.2)
        weighted += data["score"] * w
        total_weight += w
    return int(weighted / total_weight) if total_weight > 0 else 0


def _validate_audit(audit, audit_id):
    """Validate audit file structure. Raises ValueError on invalid."""
    if not isinstance(audit, dict):
        raise ValueError(f"Audit {audit_id}: root must be a dict")
    if "name" not in audit:
        raise ValueError(f"Audit {audit_id}: missing 'name' field")
    if "group_policies" not in audit:
        raise ValueError(f"Audit {audit_id}: missing 'group_policies'")
    for i, group in enumerate(audit.get("group_policies", [])):
        if "name" not in group:
            raise ValueError(f"Audit {audit_id}: group_policies[{i}] missing 'name'")
        if "items" not in group:
            raise ValueError(f"Audit {audit_id}: group_policies[{i}] missing 'items'")
        for j, item in enumerate(group.get("items", [])):
            if "id" not in item:
                raise ValueError(f"Audit {audit_id}: group_policies[{i}].items[{j}] missing 'id'")
            if "type" not in item:
                raise ValueError(f"Audit {audit_id}: item '{item.get('id')}' missing 'type'")


def clear_cache():
    """Clear the audit file cache (use after file changes)."""
    _cache.clear()
