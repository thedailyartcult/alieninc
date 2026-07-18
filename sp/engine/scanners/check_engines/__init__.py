"""
Check engines — execute audit item checks against a filesystem path.
Each engine corresponds to a `type` field in .audit.json items.

Signature: check(base_path: Path, exclude_dirs: set, item: dict) -> dict
Returns: {"status": "pass"|"fail"|"error", "detail": str, "score": int 0-100}
"""

from . import file_check, file_content_check, meta_check, pattern_check, wordcount_check, ai_review

ENGINES = {
    "FILE_CHECK": file_check.run,
    "FILE_CONTENT_CHECK": file_content_check.run,
    "META_CHECK": meta_check.run,
    "PATTERN_CHECK": pattern_check.run,
    "WORDCOUNT_CHECK": wordcount_check.run,
    "AI_REVIEW": ai_review.run,
}

def execute(base_path, exclude_dirs, item):
    engine = ENGINES.get(item.get("type", ""))
    if not engine:
        return {"status": "error", "detail": f"Unknown check type: {item.get('type')}", "score": 0}
    try:
        return engine(base_path, exclude_dirs, item)
    except Exception as e:
        return {"status": "error", "detail": f"Engine error: {e}", "score": 50}
