"""Redis infrastructure — cache and result store for simulations.

Phase 4: Infrastructure. Provides:

- `result_cache`: TTL-based JSON cache for expensive computations (Monte
  Carlo forecasts, multiverse reports) keyed by a canonical config hash.
- `universe_cache`: store/load individual universe snapshots.
- `run_log`: append-only log of simulation runs for observability.
- `healthy()`: graceful degradation — every call falls back to a no-op
  in-memory layer when Redis is unavailable, so the engine never breaks.

Redis is optional at runtime: set ALPHA_ZERO_REDIS=0 to disable entirely.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Callable, Optional

REDIS_URL = os.environ.get("ALPHA_ZERO_REDIS_URL", "redis://127.0.0.1:6379/0")
ENABLED = os.environ.get("ALPHA_ZERO_REDIS", "1") != "0"
DEFAULT_TTL = int(os.environ.get("ALPHA_ZERO_CACHE_TTL", "3600"))

_client: Optional[Any] = None
_client_ok: bool = False
_memory: dict[str, tuple[float, str]] = {}  # key -> (expires_at, payload)


def _get_client():
    global _client, _client_ok
    if _client is not None:
        return _client
    if not ENABLED:
        return None
    try:
        import redis
        _client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=2)
        _client.ping()
        _client_ok = True
    except Exception:
        _client = None
        _client_ok = False
    return _client


def healthy() -> bool:
    """True when Redis is reachable (or memory fallback in use)."""
    if not ENABLED:
        return False
    return _get_client() is not None or _client_ok


def backend() -> str:
    return "redis" if _client_ok else ("memory" if ENABLED else "disabled")


def config_hash(*parts: Any) -> str:
    """Canonical cache key from config fragments."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha1(blob).hexdigest()


def get(key: str) -> Optional[Any]:
    """Fetch a cached JSON value (Redis or memory fallback)."""
    client = _get_client()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    elif ENABLED:
        entry = _memory.get(key)
        if entry and entry[0] > time.monotonic():
            return json.loads(entry[1])
    return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """Store a JSON value with TTL."""
    payload = json.dumps(value, default=str)
    client = _get_client()
    if client is not None:
        try:
            client.set(key, payload, ex=ttl)
            return True
        except Exception:
            pass
    elif ENABLED:
        _memory[key] = (time.monotonic() + ttl, payload)
        return True
    return False


def cached(key: str, producer: Callable[[], Any], ttl: int = DEFAULT_TTL) -> tuple[Any, str]:
    """Get-or-compute with caching; returns (value, source) where source is
    'cache' or 'computed'."""
    hit = get(key)
    if hit is not None:
        return hit, "cache"
    value = producer()
    set(key, value, ttl)
    return value, "computed"


def save_universe(universe_id: str, state: dict, ttl: int = DEFAULT_TTL) -> bool:
    """Store a serialized universe snapshot."""
    return set(f"alpha_zero:universe:{universe_id}", state, ttl)


def load_universe(universe_id: str) -> Optional[dict]:
    return get(f"alpha_zero:universe:{universe_id}")


def log_run(run_type: str, config: dict, summary: dict, ttl: int = 604800) -> bool:
    """Append a run record to the run log (capped list)."""
    entry = {
        "ts": time.time(),
        "type": run_type,
        "config": config,
        "summary": summary,
    }
    client = _get_client()
    if client is not None:
        try:
            key = "alpha_zero:runs"
            client.lpush(key, json.dumps(entry, default=str))
            client.ltrim(key, 0, 999)
            client.expire(key, ttl)
            return True
        except Exception:
            pass
    return False


def recent_runs(limit: int = 20) -> list[dict]:
    """Fetch the most recent run records."""
    client = _get_client()
    if client is not None:
        try:
            raw = client.lrange("alpha_zero:runs", 0, limit - 1)
            return [json.loads(r) for r in raw]
        except Exception:
            pass
    return []


def clear() -> None:
    """Clear Alpha Zero keys (tests only)."""
    client = _get_client()
    if client is not None:
        try:
            for key in client.scan_iter("alpha_zero:*"):
                client.delete(key)
        except Exception:
            pass
    _memory.clear()
