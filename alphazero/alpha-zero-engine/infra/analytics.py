"""Monitoring & analytics store for the Alpha Zero engine and web app.

Phase 7: Monitoring & Analytics. Dependency-free, JSONL-backed analytics
store with aggregate queries. Two streams:

- `requests`: every HTTP request (method, endpoint, status, duration_ms)
- `runs`: simulation runs (single / multiverse / branch / portfolio)

Data lives under ANALYTICS_DIR (default `alpha-zero-engine/analytics_data/`,
gitignored; override with ALPHA_ZERO_ANALYTICS_DIR). Writes are thread-safe
(append + in-process lock), capped to MAX_REQUESTS / MAX_RUNS entries. The
Flask app (multiple gunicorn workers) shares the same on-disk streams, so
aggregates computed on demand reflect the whole process group.

CLI usage:
    python -m infra.analytics --summary      # JSON aggregate
    python -m infra.analytics --report       # human-readable report
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "analytics_data"
ANALYTICS_DIR = Path(os.environ.get("ALPHA_ZERO_ANALYTICS_DIR", str(DEFAULT_DIR)))
MAX_REQUESTS = int(os.environ.get("ALPHA_ZERO_ANALYTICS_MAX_REQUESTS", "5000"))
MAX_RUNS = int(os.environ.get("ALPHA_ZERO_ANALYTICS_MAX_RUNS", "1000"))

_started_at = time.time()
_lock = threading.Lock()


def set_data_dir(path: Any) -> None:
    """Point the store at a different directory (tests / deployment)."""
    global ANALYTICS_DIR
    ANALYTICS_DIR = Path(path)


def _stream(name: str) -> Path:
    return ANALYTICS_DIR / f"{name}.jsonl"


def _append(name: str, entry: dict, cap: int) -> None:
    """Append one JSON line, trimming the stream back to `cap` entries."""
    line = json.dumps(entry, default=str)
    with _lock:
        _stream(name).parent.mkdir(parents=True, exist_ok=True)
        with open(_stream(name), "a") as f:
            f.write(line + "\n")
        try:
            rows = _stream(name).read_text().splitlines()
            if len(rows) > cap:
                _stream(name).write_text("\n".join(rows[-cap:]) + "\n")
        except OSError:
            pass


def _read(name: str) -> list[dict]:
    path = _stream(name)
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def record_request(
    method: str,
    endpoint: str,
    status: int,
    duration_ms: float,
    meta: Optional[dict] = None,
) -> None:
    """Record one HTTP request."""
    entry = {
        "ts": time.time(),
        "method": method,
        "endpoint": endpoint,
        "status": status,
        "duration_ms": round(float(duration_ms), 2),
    }
    if meta:
        entry["meta"] = meta
    _append("requests", entry, MAX_REQUESTS)


def record_simulation(run_type: str, summary: dict, duration_ms: Optional[float] = None) -> None:
    """Record one simulation run (single / multiverse / branch / portfolio)."""
    entry = {"ts": time.time(), "type": run_type, "summary": summary}
    if duration_ms is not None:
        entry["duration_ms"] = round(float(duration_ms), 2)
    _append("runs", entry, MAX_RUNS)


def request_history(limit: int = 100) -> list[dict]:
    """Most recent requests (newest first)."""
    return list(reversed(_read("requests")))[:limit]


def run_history(limit: int = 50) -> list[dict]:
    """Most recent simulation runs (newest first)."""
    return list(reversed(_read("runs")))[:limit]


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[idx]


def usage_summary() -> dict:
    """Aggregate HTTP request stats over the whole stream."""
    rows = _read("requests")
    total = len(rows)
    now = time.time()
    day_ago = now - 86400
    by_endpoint: dict[str, int] = {}
    by_status: dict[str, int] = {}
    last_24h = 0
    errors = 0
    latencies: list[float] = []
    for r in rows:
        ep = r.get("endpoint", "?")
        by_endpoint[ep] = by_endpoint.get(ep, 0) + 1
        status = str(r.get("status", 0))
        by_status[status] = by_status.get(status, 0) + 1
        if r.get("ts", 0) >= day_ago:
            last_24h += 1
        if r.get("status", 0) >= 400:
            errors += 1
        latencies.append(float(r.get("duration_ms", 0)))
    latencies.sort()
    return {
        "total_requests": total,
        "last_24h_requests": last_24h,
        "error_count": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(_percentile(latencies, 0.50), 2),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "by_endpoint": dict(sorted(by_endpoint.items(), key=lambda x: x[1], reverse=True)),
        "by_status": by_status,
    }


def simulation_summary() -> dict:
    """Aggregate simulation run stats over the whole stream."""
    rows = _read("runs")
    by_type: dict[str, int] = {}
    by_strategy: dict[str, int] = {}
    total_universes = 0
    convergences: list[float] = []
    for r in rows:
        run_type = r.get("type", "?")
        by_type[run_type] = by_type.get(run_type, 0) + 1
        summary = r.get("summary") or {}
        strategy = summary.get("strategy")
        if strategy:
            by_strategy[str(strategy)] = by_strategy.get(str(strategy), 0) + 1
        universes = summary.get("universes") or 0
        try:
            total_universes += int(universes)
        except (TypeError, ValueError):
            pass
        conv = summary.get("convergence_rate")
        if conv is not None:
            try:
                convergences.append(float(conv))
            except (TypeError, ValueError):
                pass
    return {
        "total_runs": len(rows),
        "total_universes": total_universes,
        "by_type": by_type,
        "by_strategy": by_strategy,
        "avg_convergence": round(sum(convergences) / len(convergences), 4) if convergences else None,
        "runs_last_24h": sum(1 for r in rows if r.get("ts", 0) >= time.time() - 86400),
    }


def summary() -> dict:
    """Combined monitoring snapshot."""
    return {
        "uptime_seconds": round(time.time() - _started_at, 2),
        "started_at": _started_at,
        "requests": usage_summary(),
        "simulations": simulation_summary(),
    }


def reset() -> None:
    """Delete all analytics streams (tests only)."""
    with _lock:
        for name in ("requests", "runs"):
            try:
                _stream(name).unlink()
            except OSError:
                pass


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def report() -> str:
    """Human-readable monitoring report."""
    s = summary()
    u = s["requests"]
    sim = s["simulations"]
    lines = [
        "ALPHA ZERO MONITORING REPORT",
        f"Uptime: {s['uptime_seconds'] / 3600:.2f}h | Started: {time.ctime(s['started_at'])}",
        "",
        "HTTP REQUESTS",
        f"  Total: {u['total_requests']} | Last 24h: {u['last_24h_requests']}",
        f"  Errors: {u['error_count']} ({u['error_rate'] * 100:.2f}%)",
        f"  Latency: avg {u['avg_latency_ms']}ms | p50 {u['p50_latency_ms']}ms | p95 {u['p95_latency_ms']}ms",
    ]
    lines.append("  Top endpoints:")
    for ep, count in list(u["by_endpoint"].items())[:10]:
        lines.append(f"    {count:5d}  {ep}")
    lines += [
        "",
        "SIMULATION RUNS",
        f"  Total: {sim['total_runs']} | Universes: {sim['total_universes']} | Last 24h: {sim['runs_last_24h']}",
        f"  Avg convergence: {sim['avg_convergence'] if sim['avg_convergence'] is not None else 'n/a'}",
    ]
    for run_type, count in sim["by_type"].items():
        lines.append(f"    {run_type:14s} {count}")
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Alpha Zero analytics store")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--summary", action="store_true", help="print JSON aggregate")
    group.add_argument("--report", action="store_true", help="print human-readable report")
    group.add_argument("--requests", type=int, metavar="N", help="print last N requests")
    group.add_argument("--runs", type=int, metavar="N", help="print last N runs")
    parser.add_argument("--reset", action="store_true", help="wipe analytics streams")
    args = parser.parse_args()

    if args.reset:
        reset()
        print("analytics reset")
        return
    if args.summary:
        print(json.dumps(summary(), indent=2, default=str))
    elif args.report:
        print(report())
    elif args.requests is not None:
        print(json.dumps(request_history(args.requests), indent=2, default=str))
    elif args.runs is not None:
        print(json.dumps(run_history(args.runs), indent=2, default=str))
    else:
        print(report())


if __name__ == "__main__":
    main()
