"""CMB (Cognitive Memory Backend) — simple file-based memory store.

Provides persistent storage for Alpha Zero simulation results,
character states, and AI agent learnings across sessions.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


CMB_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cmb_data")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _workspace_dir(workspace: str) -> str:
    _ensure_dir(CMB_DATA_DIR)
    return os.path.join(CMB_DATA_DIR, workspace)


def _store_path(workspace: str, key: str) -> str:
    return os.path.join(_workspace_dir(workspace), f"{key}.json")


def cmb_store(workspace: str, key: str, data: Any, repo: str = "alphazero") -> str:
    """Store a piece of data in CMB memory."""
    wdir = _workspace_dir(workspace)
    _ensure_dir(wdir)
    path = _store_path(workspace, key)
    payload = {
        "key": key,
        "workspace": workspace,
        "repo": repo,
        "data": data,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return key


def cmb_retrieve(workspace: str, key: str) -> Optional[Any]:
    """Retrieve a piece of data from CMB memory."""
    path = _store_path(workspace, key)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        payload = json.load(f)
    return payload.get("data")


def cmb_list(workspace: str, repo: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all stored keys in a workspace."""
    wdir = _workspace_dir(workspace)
    if not os.path.exists(wdir):
        return []
    results = []
    for fname in sorted(os.listdir(wdir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(wdir, fname)
        with open(fpath, "r") as f:
            payload = json.load(f)
        if repo and payload.get("repo") != repo:
            continue
        results.append({
            "key": payload.get("key"),
            "workspace": payload.get("workspace"),
            "repo": payload.get("repo"),
        })
    return results


def cmb_search(workspace: str, query: str, k: int = 10) -> List[Dict[str, Any]]:
    """Search stored data by keyword in key and data content."""
    wdir = _workspace_dir(workspace)
    if not os.path.exists(wdir):
        return []
    results = []
    query_lower = query.lower()
    for fname in sorted(os.listdir(wdir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(wdir, fname)
        with open(fpath, "r") as f:
            payload = json.load(f)
        data_str = json.dumps(payload.get("data", {}), default=str).lower()
        key_str = (payload.get("key") or "").lower()
        if query_lower in key_str or query_lower in data_str:
            results.append({
                "key": payload.get("key"),
                "workspace": payload.get("workspace"),
                "repo": payload.get("repo"),
            })
    return results[:k]


def cmb_delete(workspace: str, key: str) -> bool:
    """Delete a piece of data from CMB memory."""
    path = _store_path(workspace, key)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def cmb_clear(workspace: str) -> int:
    """Clear all data in a workspace. Returns number of items deleted."""
    wdir = _workspace_dir(workspace)
    if not os.path.exists(wdir):
        return 0
    count = 0
    for fname in os.listdir(wdir):
        fpath = os.path.join(wdir, fname)
        if fname.endswith(".json"):
            os.remove(fpath)
            count += 1
    return count