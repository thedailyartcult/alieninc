"""META_CHECK engine — checks HTML <meta http-equiv="..."> tags."""

import re
from pathlib import Path


def _safe_glob(base_path, pattern):
    exclude = {".edpb-wat", "node_modules", "dist", ".git", ".backups", "__pycache__", ".cache", "build", ".angular"}
    results = []
    for fpath in base_path.glob(pattern):
        parts = fpath.relative_to(base_path).parts
        if not any(d in exclude for d in parts):
            results.append(fpath)
    return results


def _is_excluded(fpath, exclude_dirs):
    return any(exc in str(fpath) for exc in (exclude_dirs or set()))


def run(base_path, exclude_dirs, item):
    check = item.get("check", {})
    meta_name = check.get("meta_name", "")
    must_contain = check.get("must_contain", [])
    must_not_contain = check.get("must_not_contain", [])
    expected_value = check.get("expected_value")
    wildcard_forbidden_in = check.get("wildcard_forbidden_in", [])
    file_pattern = check.get("file_pattern", "**/*.html")

    meta_pattern = rf'<meta\s[^>]*http-equiv=["\']{re.escape(meta_name)}["\'][^>]*content=["\']([^"\']+)["\']|<meta\s[^>]*content=["\']([^"\']+)["\'][^>]*http-equiv=["\']{re.escape(meta_name)}["\']'

    found = False
    source_file = None
    content_value = None

    for fpath in _safe_glob(base_path, file_pattern):
        if _is_excluded(fpath, exclude_dirs):
            continue
        try:
            raw = fpath.read_text(errors="ignore")
            m = re.search(meta_pattern, raw, re.IGNORECASE)
            if m:
                content_value = m.group(1) or m.group(2)
                source_file = fpath.name
                found = True
                break
        except Exception:
            continue

    if not found:
        return {
            "status": "fail",
            "detail": f"No {meta_name} meta tag found",
            "score": 0,
        }

    issues = []
    score = 100

    if must_not_contain:
        for bad in must_not_contain:
            if bad.lower() in content_value.lower():
                issues.append(f"contains '{bad}'")
                score = max(0, score - 25)

    if must_contain:
        for required in must_contain:
            if required.lower() not in content_value.lower():
                issues.append(f"missing '{required}'")
                score = max(0, score - 25)

    if wildcard_forbidden_in:
        for directive in wildcard_forbidden_in:
            pattern = rf"{re.escape(directive)}\s+\*"
            if re.search(pattern, content_value):
                issues.append(f"wildcard in {directive}")
                score = max(0, score - 25)

    if expected_value:
        if content_value.strip().lower() != expected_value.strip().lower():
            issues.append(f"expected '{expected_value}', got '{content_value[:40]}'")
            score = 0

    if issues:
        return {
            "status": "fail" if score < 50 else "pass",
            "detail": f"{meta_name} found in {source_file} — " + "; ".join(issues),
            "score": score,
        }

    return {
        "status": "pass",
        "detail": f"{meta_name} found in {source_file} — value is compliant",
        "score": 100,
    }
