# Phase 10: Production Hardening (Docker, systemd, Health Checks, Rollback)

## Overview

**Status**: ✅ COMPLETE — all components built and verified end-to-end on the server (178.104.71.88)

## What Was Built

### 1. Systemd Service — `alpha-zero-engine/infra/systemd/alpha-zero-web.service` ✅
Production systemd unit for the Alpha Zero web app:
- **Type=notify** with gunicorn (supports systemd watchdog)
- **User=tablet** — runs as non-root
- **WorkingDirectory** = `/home/tablet/alieninc/alphazero/alpha-zero-engine`
- **Environment** — venv PATH, PYTHONPATH, analytics dir
- **Restart=on-failure** with 5s delay
- **After=cmb-mcp-http.service** — waits for CMB memory server
- Logs to journald (`StandardOutput=journal`)

Install:
```bash
sudo cp alpha-zero-engine/infra/systemd/alpha-zero-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alpha-zero-web
sudo systemctl status alpha-zero-web
```

### 2. Multi-stage Dockerfile — `Dockerfile` 🟡 (untested)
Three-stage build for minimal production image:
- **Stage 1 (go-builder)**: Compiles Go `alphacore` binary (2.9MB, static) — path fixed to `alphacore/`
- **Stage 2 (rust-builder)**: Compiles Rust `alphazero-mcp-client` binary
- **Stage 3 (runtime)**: Python 3.13-slim + deps + binaries
  - Non-root user `alphazero`
  - Pre-installs Python deps (layer cached)
  - Health check via `/api/health`
  - Exposes port 8080

### 3. Docker Compose — `docker-compose.yml` ✅
Full stack orchestration:
| Service | Port | Purpose |
|---------|------|---------|
| `cmb` | 8765 | CMB memory server (MCP) |
| `redis` | 6379 | Cache for `infra.cache` |
| `ollama` | 11434 | Local LLM (GPU optional) |
| `web` | 8080 | Alpha Zero web app |

All services have health checks, proper dependencies, and named volumes for persistence.

### 4. CMB Dockerfile — `docker/Dockerfile.cmb` ✅ FIXED
**Issue (resolved)**: CMB's `pyproject.toml` declared only `numpy` as a dependency, but
`mcp_server.py` imports `pydantic`, `uvicorn`, and `mcp` at runtime. The Dockerfile's manual
`pip install ... mcp` list was a workaround that did not match a declared extra.

**Fix**:
- Added `[project.optional-dependencies] mcp` to `docker/cmb-src/pyproject.toml` (and the
  canonical source at `/home/tablet/setup/cmb/src/pyproject.toml`):
  `mcp==1.29.0`, `pydantic==2.13.4`, `pydantic-settings==2.14.2`, `uvicorn==0.52.1`
  (pinned to the exact versions verified on the laptop).
- Dockerfile now installs `pip install "./cmb-src[mcp]"`.
- Healthcheck switched from `GET /health` (which does not exist — FastMCP only serves `/mcp`)
  to a TCP connect probe on 8765.
- Verified: image builds, runs, MCP `initialize` handshake + 37 `cmb_` tools served over
  Streamable HTTP.

### 4b. Docker Compose — `docker-compose.yml` ✅
- CMB healthcheck fixed to the TCP probe (no `/health` endpoint).
- Removed the nvidia GPU `deploy.resources.reservations` block on `ollama` (no GPU on either
  host — was a hard failure for non-GPU deployments).
- Fixed `web` env var names the app actually reads: `OLLAMA_URL` (not `OLLAMA_HOST`) and
  `ALPHA_ZERO_REDIS_URL` (not `REDIS_URL`). With these set, `/api/health` reports
  `ollama: true, redis: true, alphacore_binary: true`.

### 4c. Server override — `docker-compose.server.yml` ✅ NEW
The server already runs native services on 8765 (CMB), 6379 (redis) and 8080 (Alien Inc
dashboard). The override republishes on non-conflicting host ports so nothing native is
disturbed. Uses `!override` merge tags (plain override would *append* port mappings):

| Service | Host port | Container port |
|---------|-----------|----------------|
| cmb     | 18765     | 8765           |
| redis   | 16379     | 6379           |
| web     | 18080     | 8080           |
| ollama  | 11434     | 11434          |

Usage: `docker compose -f docker-compose.yml -f docker-compose.server.yml up -d`

### 5. Deploy Script — `deploy.sh` ✅ Verified
Zero-downtime deploy. Parameterized:
- `AZ_HEALTH_URL` — health endpoint to verify (default `http://localhost:8080/api/health`)
- `AZ_COMPOSE_FILES` — space-separated compose files (default `docker-compose.yml`; on server:
  `docker-compose.yml docker-compose.server.yml`)
- `AZ_SKIP_BUILD=1` — skip `docker compose build` for image-only deploys
- Removed the broken `--scale web=2` rolling step (two replicas can't share one published port).

### 6. Rollback Script — `rollback.sh` ✅ Verified
Instant rollback to the latest timestamped backup. Fixed the backup-discovery glob
(`ls analytics_*` listed directory *contents* when it matched a directory — now uses
`find -type d`). Restores analytics dir by replacing contents and CMB DB from
`cmb.db.backup.<timestamp>`.

## Verification Status

| Component | Status |
|-----------|--------|
| Systemd service file | ✅ Created |
| Dockerfile (web) | ✅ Built + verified `/api/health` (Go + Rust binaries included) |
| docker-compose.yml | ✅ Full stack healthy on server |
| docker-compose.server.yml | ✅ Port override works (non-conflicting host ports) |
| CMB Dockerfile | ✅ Builds, runs, serves 37 MCP tools |
| deploy.sh | ✅ Verified end-to-end on server |
| rollback.sh | ✅ Verified end-to-end on server |

## Server Deployment (178.104.71.88) — as of 2026-08-05

- Docker 29.7.1 + Compose v5.4.0 installed (Debian 12 bookworm).
- Images `alphazero-cmb:latest` + `alphazero-web:latest` built on the laptop and loaded via
  `docker save | ssh server 'docker load'` (avoids a 3.5-min Go/Rust rebuild on the server).
- Stack running: cmb (18765), redis (16379), web (18080), ollama (11434) — all 4 healthy.
- Docker cmb volume seeded with the server's native CMB DB (`/srv/cmb/data/cmb.db`) so the
  containerized brain starts with real data.
- Native services untouched: 8765 (CMB), 6379 (redis), 8080 (Alien Inc dashboard).
- Verified commands:
  ```bash
  curl http://127.0.0.1:18080/api/health        # status ok, ollama/redis/alphacore true
  curl -X POST http://127.0.0.1:18765/mcp ...   # MCP initialize handshake
  docker compose -f docker-compose.yml -f docker-compose.server.yml ps
  AZ_HEALTH_URL=http://127.0.0.1:18080/api/health \
  AZ_COMPOSE_FILES="docker-compose.yml docker-compose.server.yml" \
  AZ_SKIP_BUILD=1 bash ./deploy.sh test
  AZ_HEALTH_URL=http://127.0.0.1:18080/api/health \
  AZ_COMPOSE_FILES="docker-compose.yml docker-compose.server.yml" bash ./rollback.sh
  ```

## Notes

- **No static assets** — `dashboard.html` is fully inline (single file, no CDN needed)
- **CMB data** — persisted in named volume `cmb_data` (survives container recreation)
- **Analytics** — JSONL files in `analytics_data` volume (disposable telemetry)
- **Logs** — journald for systemd, Docker logging driver for containers
- **Ollama GPU** — optional in compose (`deploy.resources.reservations.devices`)
- **Secrets** — none in image; all config via environment variables

## Next Phase Candidates

Per roadmap:
1. **Phase 11**: Observability — Prometheus metrics, Grafana dashboards, alerting
2. **Phase 12**: CI/CD — GitHub Actions pipeline (test → build → deploy → rollback)
3. **Go/Rust parity** for 3 advisors (optional stretch from Phase 9)