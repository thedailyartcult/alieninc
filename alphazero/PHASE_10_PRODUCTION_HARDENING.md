# Phase 10: Production Hardening (Docker, systemd, Health Checks, Rollback)

## Overview

**Status**: 🟡 PARTIAL — systemd, compose, deploy/rollback scripts DONE; CMB Docker image BLOCKED on missing deps

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

### 4. CMB Dockerfile — `docker/Dockerfile.cmb` 🔴 BLOCKED
**Issue**: CMB's `pyproject.toml` declares only `numpy` as dependency, but `mcp_server.py` imports `pydantic`, `fastapi`, `uvicorn`, `mcp` at runtime.

**Current workaround in Dockerfile** (line 12):
```dockerfile
RUN pip install --no-cache-dir ./cmb-src pydantic pydantic-settings fastapi uvicorn mcp
```

**Still failing** with: `The 'mcp' package is required to run the CMB MCP server.`

**Root cause**: The CMB source bundle at `/home/tablet/setup/cmb/src` (copied to `docker/cmb-src/`) is missing transitive dependencies. The `cmb[mcp]` extra or `mcp` package itself isn't being pulled in correctly.

**To fix on server**:
```bash
# Check what cmb[mcp] extra pulls
pip install "cmb[mcp]" --dry-run

# Or patch pyproject.toml in the source bundle before build:
# [project.optional-dependencies]
# mcp = ["mcp", "pydantic", "pydantic-settings", "fastapi", "uvicorn"]
```

### 5. Deploy Script — `deploy.sh` ✅
Zero-downtime rolling deploy with backup/verify/rollback.

### 6. Rollback Script — `rollback.sh` ✅
Instant rollback to timestamped backup.

## Verification Status

| Component | Status |
|-----------|--------|
| Systemd service file | ✅ Created |
| Dockerfile (web) | 🟡 Syntax OK, unbuilt |
| docker-compose.yml | ✅ Config validates |
| CMB Dockerfile | 🔴 Build fails (missing deps) |
| deploy.sh / rollback.sh | ✅ Created + executable |

## Next Steps (on server)

1. **Fix CMB image**: Patch `docker/cmb-src/pyproject.toml` to include `mcp` extra deps, rebuild
2. **Test full stack**: `docker compose up -d` → verify all 4 services healthy
3. **Verify web health**: `curl http://localhost:8080/api/health`
4. **Test deploy/rollback**: `./deploy.sh test` → `./rollback.sh`

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