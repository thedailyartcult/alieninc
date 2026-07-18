"""PATTERN_CHECK engine — multi-file regex pattern matching with scoring."""

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


def _read_files(base_path, pattern, exclude_dirs):
    """Read all matching files and return concatenated text content."""
    chunks = []
    for fpath in _safe_glob(base_path, pattern):
        if _is_excluded(fpath, exclude_dirs):
            continue
        try:
            chunks.append(fpath.read_text(errors="ignore"))
        except Exception:
            pass
    return "\n".join(chunks), len(chunks)


def run(base_path, exclude_dirs, item):
    check = item.get("check", {})
    patterns = check.get("patterns", [])
    anti_patterns = check.get("anti_patterns", [])
    file_pattern = check.get("file_pattern", "**/*.html")
    min_patterns = check.get("min_patterns")
    strip_html = check.get("strip_html", False)
    mode = check.get("mode", "count")  # "count", "scored", "presence"

    content, file_count = _read_files(base_path, file_pattern, exclude_dirs)
    if strip_html:
        content = re.sub(r"<[^>]+>", " ", content)
    content_lower = content.lower()

    if mode == "scored":
        matched = 0
        total = len(patterns)
        match_details = []
        for p in patterns:
            if re.search(p.lower(), content_lower):
                matched += 1
            else:
                match_details.append(p[:50])
        if total == 0:
            return {"status": "pass", "detail": "No patterns to check", "score": 100}
        score = int((matched / total) * 100)
        if match_details:
            return {
                "status": "fail" if score < 70 else "pass",
                "detail": f"{matched}/{total} patterns matched ({score}%) — missing: " + "; ".join(match_details[:3]),
                "score": score,
            }
        return {"status": "pass", "detail": f"All {total} patterns matched ({score}%)", "score": score}

    if mode == "presence" or mode == "any":
        found = []
        missing = []
        for p in patterns:
            if re.search(p.lower(), content_lower):
                found.append(p[:40])
            else:
                missing.append(p[:40])
        # Check anti_patterns
        anti_issues = []
        for p in anti_patterns:
            m = re.search(p.lower(), content_lower)
            if m:
                anti_issues.append("prohibited '{}'".format(m.group(0)[:60]))
        if anti_issues:
            return {"status": "fail", "detail": "; ".join(anti_issues[:3]), "score": 0}
        if mode == "any":
            if found:
                return {"status": "pass", "detail": "{}/{} patterns found".format(len(found), len(patterns)), "score": 100}
            else:
                return {"status": "fail", "detail": "0/{} patterns matched".format(len(patterns)), "score": 0}
        if missing:
            return {
                "status": "fail",
                "detail": "{}/{} patterns present — missing: ".format(len(found), len(patterns)) + "; ".join(missing[:4]),
                "score": int((len(found) / len(patterns)) * 100) if patterns else 100,
            }
        return {"status": "pass", "detail": f"All {len(patterns)} patterns present across {file_count} files", "score": 100}

    # mode == "count"
    total_matches = 0
    for p in patterns:
        matches = len(re.findall(p.lower(), content_lower))
        total_matches += matches

    if min_patterns is not None and total_matches < min_patterns:
        return {
            "status": "fail",
            "detail": f"{total_matches} total matches — minimum {min_patterns} required across {file_count} files",
            "score": 0,
        }

    anti_issues = []
    for p in anti_patterns:
        m = re.search(p.lower(), content_lower)
        if m:
            anti_issues.append(f"found prohibited '{m.group(0)[:40]}'")

    if anti_issues:
        return {"status": "fail", "detail": "; ".join(anti_issues[:3]), "score": 0}

    return {
        "status": "pass",
        "detail": f"{total_matches} matches across {file_count} files" if patterns else "Check passed (negative check)",
        "score": 100,
    }
