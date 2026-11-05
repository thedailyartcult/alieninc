# Phase 9: Persistent Advisor Panel & Cross-Session Continuity

## Overview

**Status**: ✅ COMPLETE — implemented, tested (10 tests pass with `OLLAMA_DISABLE=1`), and committed as `40fa7cf8d`

## What Was Built

### 1. Advisor Dossier — `alphazero/ai/advisor_dossier.py`
Durable per-character dossier persisted via CMB (MemorySystemAgent). Four core functions:

- **`build_continuity(character_id)`** — assembles deterministic continuity block: `{character_id, prior_advice: [financial, health, mentor], simulation_summary, updated_at}` — used as context prefix by all three specialist agents
- **`merge_character_state(interview, multiverse, character)`** — merges interview JSON, multiverse summary, and engine character state into a single `character_state` dict stored in CMB
- **`recall_prior_advice(character_id)`** — retrieves the last stored advice from each specialist for continuity injection
- **`recall_advisor_dossier(character_id)`** — full dossier retrieval for the web API

Storage: CMB keys `advisor_dossier:<character_id>` and `advisor_advice:<character_id>:<advisor>`, TTL none (durable). CLI: `python -m ai.advisor_dossier --character-id <id> [--recall|--clear]`

### 2. Advisor Panel Orchestrator — `alphazero/ai/advisor_panel.py`
**`run_advisor_panel(interview_data)`** — single entry point that chains:
1. **Interview** → structured persona/profile/social_variables/status
2. **Multiverse** → 15-universe simulation (configurable, deterministic with seed)
3. **Character state** → merge interview + multiverse + engine state via `merge_character_state`
4. **Recall** → pull prior advice via `recall_prior_advice` for continuity
5. **Three specialists** → FinancialAdvisor, HealthCoach, Mentor each receive continuity block via `build_continuity`
6. **Store dossier** → persist merged state + all three advisor outputs via CMB

JSON CLI: `python -m ai.advisor_panel <interview.json>` → prints complete panel result

### 3. Specialist Agents — Continuity Integration
All three Phase 8 agents modified (2 lines each) to accept and prepend continuity block:

- **`alphazero/ai/financial_advisor.py`** — `generate_advice(profile, continuity=None)`
- **`alphazero/ai/health_coach.py`** — `generate_advice(profile, continuity=None)`
- **`alphazero/ai/mentor.py`** — `synthesize(financial, health, continuity=None)`

Continuity block format injected into prompt:
```
[CONTINUITY — prior advice]
Financial: {...}
Health: {...}
Mentor: {...}
[END CONTINUITY]
```

### 4. Pipeline Memory Stage Extended — `alphazero/ai/pipeline.py`
- **Self-bootstrapping sys.path** — works from any CWD (repo root, engine dir, etc.)
- **`advisor_outputs` in memory stage** — pipeline's `memory` stage now stores each advisor's full output (not just the analysis insight) under `advisor_outputs: {financial_advisor, health_coach, mentor}`
- **Prior advice recall** — `run_ai_pipeline` calls `recall_prior_advice(character_id)` and passes continuity to all three agents

### 5. Web API — `alphazero/alpha-zero-engine/api/routes.py`
Two new POST endpoints (total 18 endpoints):

- **`POST /api/ai/advisors`** — runs full advisor panel for a character
  - Input: `{interview_data, character_id?, universes?}`
  - Output: `{character_id, interview, multiverse_summary, character_state, advisors: {financial_advisor, health_coach, mentor}, dossier_id}`
- **`POST /api/ai/advisor_dossier`** — retrieves persisted dossier
  - Input: `{character_id}`
  - Output: full dossier from CMB

### 6. Dashboard Advisors Tab — `alphazero/alpha-zero-engine/web/templates/dashboard.html`
New "Advisors" tab with:
- Character ID input + Interview JSON textarea (pre-filled example)
- Universes selector (default 15)
- "Run Advisor Panel" button → calls `/api/ai/advisors`
- Results display: character state summary + three advisor cards (Financial, Health, Mentor)
- "Load Dossier" button → calls `/api/ai/advisor_dossier` for continuity verification

## Tests

`test_ai_integration.py` — **10 new Phase 9 tests, all passing**:

| Test | Purpose |
|------|---------|
| `test_financial_advisor_advice` | Financial advisor generates valid JSON with continuity |
| `test_mentor_synthesizes_advisors` | Mentor synthesizes financial + health with continuity |
| `test_advisor_panel_cli` | Full panel CLI: interview → multiverse → 3 advisors |
| `test_advisor_continuity_recall` | Prior advice recalled and injected into continuity block |
| `test_advisor_dossier_recall` | Dossier persisted and retrievable via CMB |
| `test_pipeline_stores_advisor_outputs` | Pipeline memory stage stores all 3 advisor outputs |
| `test_web_ai_financial_advisor_route` | `/api/ai/financial_advisor` endpoint works |
| `test_web_ai_pipeline_route` | `/api/ai/pipeline` 15-universe integration test (slow) |
| `test_web_ai_advisors_route` | `/api/ai/advisors` full panel endpoint |
| `test_web_ai_advisor_dossier_route` | `/api/ai/advisor_dossier` retrieval endpoint |

Run:
```bash
cd /home/tablet/alieninc/alphazero
OLLAMA_DISABLE=1 /home/tablet/az-venv/bin/python -m pytest test_ai_integration.py -v -k "advisor or panel or dossier or pipeline"
```

## Run

### CLI (no web server needed)
```bash
# from repo root
cd /home/tablet/alieninc/alphazero

# Full advisor panel via interview JSON
cat > /tmp/interview.json <<'EOF'
{"name":"Test User","age":25,"personality":{"openness":70,"conscientiousness":60,"extraversion":50,"agreeableness":65,"neuroticism":30},"goals":["financial independence","health optimization"],"risk_tolerance":6}
EOF
OLLAMA_DISABLE=1 python -m ai.advisor_panel /tmp/interview.json

# Recall dossier for continuity verification
OLLAMA_DISABLE=1 python -m ai.advisor_dossier --character-id <uuid-from-above>
```

### Web (requires gunicorn)
```bash
# Deploy (restart gunicorn to pick up new routes)
/home/tablet/start-alpha-zero.sh   # after stopping old master

# Verify live endpoints
curl -s -X POST http://127.0.0.1:8080/api/ai/advisors \
  -H "Content-Type: application/json" \
  -d '{"interview_data":{"name":"Test","age":25,"personality":{"openness":70,"conscientiousness":60,"extraversion":50,"agreeableness":65,"neuroticism":30},"goals":["FIRE"],"risk_tolerance":6},"universes":15}'

curl -s -X POST http://127.0.0.1:8080/api/ai/advisor_dossier \
  -H "Content-Type: application/json" \
  -d '{"character_id":"<uuid-from-above>"}'
```

## Verification Checklist (No Junk Files)

- [ ] All 10 Phase 9 tests pass with `OLLAMA_DISABLE=1`
- [ ] `git status` clean (only `PHASE_9_ADVISOR_PANEL.md` as new file)
- [ ] No files in `/tmp` created by tests (they use CMB/temp dirs properly)
- [ ] Dashboard Advisors tab loads at `http://127.0.0.1:8080`
- [ ] `/api/ai/advisors` returns character_id + all 3 advisors + dossier_id
- [ ] `/api/ai/advisor_dossier` returns same data with prior_advice populated on second run
- [ ] CMB keys `advisor_dossier:*` and `advisor_advice:*` exist and are queryable

## Notes

- **Pre-existing failures still NOT to chase**: `test_event_balance` (avg_lifespan 55.1<60), `test_infra` (needs Redis)
- **Ollama**: Tests use `OLLAMA_DISABLE=1` for deterministic fast runs. Production uses local Ollama (gemma2:2b, llama3.2:latest) on laptop only.
- **CMB**: All dossier/advice state lives in CMB (`alphazero` workspace, `alphazero` repo) — not in code or local files. Survives restarts, deployments, and cross-session.
- **Go/Rust parity**: OPTIONAL stretch — not implemented. Phase 8 added 5 Go `alphacore` AI commands + Rust MCP bridge handlers for interview/coach/analyze/narrate/memory. Same could be done for financial_advisor/health_coach/mentor if needed.

## Next Phase Candidates

Per roadmap memory:
1. **Phase 10**: Production hardening (Docker, systemd, health checks, rollback)
2. **Go alphacore + Rust MCP parity** for the 3 new advisors (optional stretch)
3. **Advanced multiverse analytics** (convergence clustering, strategy comparison UI)