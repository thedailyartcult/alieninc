import os
import re
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from panteon.core.auth import SupabaseUser, get_current_user
from panteon.core.config import settings

router = APIRouter(prefix="/research", tags=["Research"])

# Only safe URL-safe slug characters — blocks path traversal.
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,100}$")


def _locked_dir() -> Path:
    configured = (settings.locked_research_dir or "").strip()
    if configured:
        return Path(configured)
    # Default: <panteon>/data/research-locked — outside the public web root.
    backend_dir = Path(os.path.dirname(__file__)).resolve().parent.parent  # backend/
    return backend_dir.parent / "data" / "research-locked"


@router.get("/{slug}")
async def get_locked_article(
    slug: str,
    current_user: SupabaseUser = Depends(get_current_user),
):
    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Article not found")

    article_path = _locked_dir() / f"{slug}.json"
    if not article_path.is_file():
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        with open(article_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Article content unavailable")

    return {
        "slug": payload.get("slug", slug),
        "title": payload.get("title", ""),
        "date": payload.get("date", ""),
        "author": payload.get("author", ""),
        "html": payload.get("html", ""),
    }
