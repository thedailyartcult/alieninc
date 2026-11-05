"""
Feed Budget router — exposes per-feed daily quota status.
"""

import sys
import os
from fastapi import APIRouter
from typing import Any, Dict

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from feed_budget import feed_budget

router = APIRouter(prefix="/feed-budget", tags=["feed-budget"])

FEEDS = [
    {"name": "opensky", "max_per_day": 10},
    {"name": "gdelt", "max_per_day": 20},
    {"name": "firms", "max_per_day": 50},
    {"name": "vessels", "max_per_day": 10},
]

@router.get("")
async def get_feed_budget() -> Dict[str, Any]:
    """Return budget status for all registered feeds."""
    result = {}
    for f in FEEDS:
        result[f["name"]] = feed_budget.status(f["name"], f["max_per_day"])
    return result
