"""FILE_CONTENT_CHECK engine — regex-based content search in HTML/JS/TXT files."""

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
    patterns = check.get("patterns", [])
    anti_patterns = check.get("anti_patterns", [])
    file_pattern = check.get("file_pattern", "**/*.html")
    min_matches = check.get("min_matches", 1)
    mode = check.get("mode", "any")  # "any" = OR, "all" = AND
    strip_html = check.get("strip_html", False)

    found_in = {}
    anti_found = {}
    glob_pattern = file_pattern if file_pattern.startswith("**/") else f"**/{file_pattern}"

    for fpath in _safe_glob(base_path, glob_pattern):
        if _is_excluded(fpath, exclude_dirs):
            continue
        try:
            content = fpath.read_text(errors="ignore").lower()
            if strip_html:
                content = re.sub(r"<[^>]+>", " ", content)

            matches = []
            for p in patterns:
                if re.search(p.lower(), content):
                    matches.append(p)
            if matches:
                found_in[str(fpath.relative_to(base_path))] = matches

            if anti_patterns:
                anti_matches = []
                for p in anti_patterns:
                    m = re.search(p.lower(), content)
                    if m:
                        anti_matches.append({"pattern": p, "value": m.group(0)[:60]})
                if anti_matches:
                    anti_found[str(fpath.relative_to(base_path))] = anti_matches
        except Exception:
            continue

    failures = []

    if mode == "all":
        missing = []
        for p in patterns:
            if not any(p in matches for matches in found_in.values()):
                missing.append(p)
        if missing:
            failures.append(f"Missing {len(missing)} required patterns")
    elif patterns:
        total_matches = sum(len(v) for v in found_in.values())
        if total_matches < min_matches:
            failures.append(f"Only {total_matches}/{min_matches} required matches found")

    if anti_found:
        for fpath, amatches in anti_found.items():
            for am in amatches[:2]:
                failures.append(f"{am['pattern']} → '{am['value']}' in {fpath.split('/')[-1]}")

    if failures:
        return {"status": "fail", "detail": "; ".join(failures[:4]), "score": 0}

    detail = f"All patterns matched in {len(found_in)} file(s)" if found_in else f"No patterns needed — {len(patterns)} checked"
    return {"status": "pass", "detail": detail, "score": 100}
