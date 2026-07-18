"""FILE_CHECK engine — checks file existence, optionally with content requirements."""

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
    file_paths = check.get("file_paths", [])
    option = check.get("option", "MUST_EXIST")
    must_contain = check.get("must_contain")
    must_not_contain = check.get("must_not_contain")
    scan_subdirs = check.get("scan_subdirs", True)

    found = []
    if scan_subdirs:
        for fpath in _safe_glob(base_path, "**/*"):
            if _is_excluded(fpath, exclude_dirs):
                continue
            for fp in file_paths:
                if fpath.name == fp or str(fpath.relative_to(base_path)).endswith(fp):
                    found.append(fpath)
    else:
        for fp in file_paths:
            check_path = base_path / fp
            if check_path.exists():
                found.append(check_path)

    # Also check .well-known/ variants
    for fp in file_paths:
        well_known = base_path / ".well-known" / fp
        if well_known.exists() and well_known not in found:
            found.append(well_known)

    if option == "MUST_EXIST":
        if not found:
            return {
                "status": "fail",
                "detail": f"Required files not found: {', '.join(file_paths)}",
                "score": 0,
            }

    if option == "MUST_NOT_EXIST":
        if found:
            rels = [str(f.relative_to(base_path)) for f in found]
            return {
                "status": "fail",
                "detail": f"Sensitive files exposed: {', '.join(rels[:5])}",
                "score": 0,
            }
        return {"status": "pass", "detail": "No sensitive files exposed", "score": 100}

    content_results = []
    if must_contain:
        for fpath in found:
            try:
                content = fpath.read_text(errors="ignore")
                if must_contain not in content:
                    content_results.append(f"missing '{must_contain}' in {fpath.name}")
            except Exception:
                pass
    if must_not_contain:
        for fpath in found:
            try:
                content = fpath.read_text(errors="ignore")
                if must_not_contain in content:
                    content_results.append(f"found prohibited '{must_not_contain}' in {fpath.name}")
            except Exception:
                pass

    if must_contain or must_not_contain:
        if content_results:
            return {"status": "fail", "detail": "; ".join(content_results[:3]), "score": 0}
        return {"status": "pass", "detail": "All content requirements met", "score": 100}

    if found:
        rels = [str(f.relative_to(base_path)) for f in found[:3]]
        return {"status": "pass", "detail": f"Found: {', '.join(rels)}", "score": 100}

    if option == "MUST_EXIST":
        return {"status": "fail", "detail": f"No matching files found for: {', '.join(file_paths)}", "score": 0}

    return {"status": "pass", "detail": "Check passed (no files matched NOT_EXIST)", "score": 100}
