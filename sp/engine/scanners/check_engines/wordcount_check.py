"""WORDCOUNT_CHECK engine — measures word count in designated files with thresholds."""

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


def _count_words(fpath):
    try:
        content = fpath.read_text(errors="ignore")
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return len(text.split())
    except Exception:
        return 0


def run(base_path, exclude_dirs, item):
    check = item.get("check", {})
    file_names = check.get("file_names", ["privacy", "privacy-policy"])
    thresholds = check.get("thresholds", {})
    strip_html = check.get("strip_html", True)

    found_files = []
    total_words = 0

    for fname in file_names:
        for ext in check.get("extensions", [".html", ".md", ".php"]):
            check_path = base_path / (fname + ext)
            if check_path.exists():
                if not _is_excluded(check_path, exclude_dirs):
                    found_files.append(check_path)
        for fpath in _safe_glob(base_path, f"**/{fname}*"):
            if _is_excluded(fpath, exclude_dirs):
                continue
            if fpath.suffix in check.get("extensions", [".html", ".md", ".php"]):
                if fpath not in found_files:
                    found_files.append(fpath)

    for fpath in found_files:
        words = _count_words(fpath) if strip_html else len(fpath.read_text(errors="ignore").split())
        total_words += words

    if not found_files:
        return {
            "status": "fail",
            "detail": f"No matching files found for: {', '.join(file_names)}",
            "score": 0,
        }

    excellent = thresholds.get("excellent", 3000)
    good = thresholds.get("good", 1500)
    minimum = thresholds.get("minimum", 500)

    if total_words >= excellent:
        score = 100
        rating = "excellent"
    elif total_words >= good:
        score = 75
        rating = "good"
    elif total_words >= minimum:
        score = 50
        rating = "minimal"
    else:
        score = 0
        rating = "insufficient"

    detail = f"{total_words} words ({rating}) across {len(found_files)} file(s)"
    return {"status": "fail" if score < 50 else "pass", "detail": detail, "score": score}
