# Phase 7: Monitoring & Analytics

## Overview

**Status**: ✅ COMPLETE — implemented, tested, and verified live against the deployed app on :8080

## What Was Built

### 1. Analytics store — `alpha-zero-engine/infra/analytics.py`
Dependency-free, JSONL-backed telemetry store. Two streams, shared across
all gunicorn workers (multi-process safe at the append level):

- **`requests.jsonl`** — every HTTP request (ts, method, endpoint, status, duration_ms), capped at 5000 entries.
- **`runs.jsonl`** — every simulation run (single / multiverse / branch) with summary + duration_ms, capped at 1000 entries.

Storage defaults to `alpha-zero-engine/analytics_data/` (gitignored), overridable via
`ALPHA_ZERO_ANALYTICS_DIR` (used by tests and the CLI). Writes are thread-safe
(in-process lock + append), streams are auto-trimmed.

Aggregates:
- `usage_summary()` — total/last-24h requests, error rate, avg/p50/p95 latency, by-endpoint, by-status
- `simulation_summary()` — total runs, total universes, by-type, by-strategy, avg convergence
- `summary()` — combined snapshot with uptime

CLI (works without the web app):
```bash
cd alpha-zero-engine
python -m infra.analytics --summary      # JSON aggregate
python -m infra.analytics --report       # human-readable report
python -m infra.analytics --requests 20  # last 20 requests
python -m infra.analytics --runs 10      # last 10 runs
```

### 2. Flask monitoring — `alpha-zero-engine/api/routes.py`
- **Request hooks** (`before_request`/`after_request`) record timing + status for every
  request. `/api/health` and `/api/analytics/*` exclude themselves from the stream.
- **`GET /api/health`** — liveness: uptime, pid, RSS MB (from /proc), request/error counts,
  dependency status (Ollama via /api/tags, Redis via infra.cache, Go core binary presence).
- **`GET /api/analytics/summary`** — combined requests + simulations snapshot.
- **`GET /api/analytics/requests?limit=N`** — recent request log (default 100).
- **`GET /api/analytics/runs?limit=N`** — recent simulation runs (default 50).
- Simulation handlers (`/api/simulate`, `/api/multiverse`, `/api/branch`) now also
  record a structured run entry.

### 3. Engine CLI analytics — `alpha-zero-engine/main.py`
`--mode single` and `--mode multiverse` record their runs into the same store, so
engine-side CLI usage is tracked alongside web usage.

### 4. Dashboard Monitor tab — `alpha-zero-engine/web/templates/dashboard.html`
New "Monitor" tab with live cards: engine health + uptime, dependency status
dots, request/error counters, latency (avg/p50/p95), run + universe totals,
top-endpoints list, and a recent-runs table. Auto-refreshes every 15s and via
the Refresh button.

## Tests

`test_monitoring.py` — 9 tests, all passing:
- Store: record/summary aggregation, latency percentiles, stream capping, reset
- Endpoints: /api/health, /api/analytics/summary, /api/analytics/runs
- Self-exclusion: health/analytics calls don't pollute the request stream
- Dashboard: Monitor tab + refresh button present
- CLI: `python -m infra.analytics --summary` subprocess

Existing web routes re-verified (`test_ai_integration.py -k "web and not pipeline"` = 6 passed).

## Run

```bash
# from repo root
/home/tablet/az-venv/bin/python -m pytest test_monitoring.py -v

# deploy (restart gunicorn to pick up new code)
/home/tablet/start-alpha-zero.sh   # after stopping the old master process

# verify live
curl -s http://127.0.0.1:8080/api/health
curl -s http://127.0.0.1:8080/api/analytics/summary
```

## Notes
- Pre-existing failures still NOT to chase: `test_event_balance` (avg_lifespan 55.1<60), `test_infra` (needs Redis).
- Analytics data is disposable runtime telemetry (gitignored); `python -m infra.analytics --reset` wipes it.
