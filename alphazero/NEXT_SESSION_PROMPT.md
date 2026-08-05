# NEXT SESSION PROMPT — Phase 8: Advisor Go/Rust Parity + MCP Tools

Paste this entire block to the next AI model (with your CMB session setup) to
resume work with zero context loss.

---

You are continuing Alpha Zero development. Run your CMB MCP session protocol
first (`cmb_health`, `cmb_check_update`, `cmb_recall_proactive(workspace='alieninc', repo='alphazero', k=5)`,
`cmb_start_session(workspace='alieninc', repo='alphazero', goal='<your goal>')`).

## Context you must recall from CMB first
- `mem_01KZ91747BFYDY0P9MKN1S138T` — mcp_server.py ownership: the Alpha Zero
  engine's `alpha-zero-engine/mcp_server.py` is standalone; NEVER copy it into
  `docker/cmb-src/cmb/` or `docker/cmb-src/build/lib/` (those belong to the
  separate CMB memory engine package, tracked at git HEAD, md5 d12901ad).
- `mem_01KZ91FGYBJN1FZAB5F09VFRDG` — Phase 8 advisor MCP tools registered in
  `alpha-zero-engine/mcp_server.py`.
- `mem_01KZ91FSHZ57NJ0SVMEQV9SWSN` — `finance/native.py::native_advisor` wrapper
  + 21 advisor parity tests.
- `mem_01KZ91G41H0A5X3TFGDFJ387HW` — PRE-EXISTING failing test
  `test_full_life_balance_avg_lifespan` (avg lifespan 55.1 < 60, seed 42).
- `mem_01KZ91747BFYDY0P9MKN1S138T` (read again): docker/cmb-src is the CMB
  package — never touched by Alpha Zero changes.

## What is DONE (verified this session)
1. **Go alphacore** (`alpha-zero-engine/core/alphacore/main.go`): new commands
   `advisor_financial | advisor_health | advisor_mentor` — deterministic ports
   of the Python heuristic cores (`ai/financial_advisor.py`,
   `ai/health_coach.py`, `ai/mentor.py`), with `buildContinuity`,
   `analyzeFinancialState`, `normalizedHealth`, `pyRound`, `commaInt`,
   strategies map, etc. Bit-exact parity vs Python (`OLLAMA_DISABLE=1`).
2. **Rust mcp-client** (`rust/mcp-client/src/lib.rs`): handlers
   `rust_financial_advisor_handler`, `rust_health_coach_handler`,
   `rust_mentor_handler` bridge to the Python agents via `agent_command`
   (JSON in/out); wired `"financial_advisor" | "health_coach" | "mentor"` into
   `handle_command`. `cargo test`: 5 passed.
3. **Engine MCP server** (`alpha-zero-engine/mcp_server.py`): tools
   `alpha_zero_financial_advisor`, `alpha_zero_health_coach`,
   `alpha_zero_mentor` (handlers + TOOL_HANDLERS + @server.tool defs). Smoke-tested.
4. **native wrapper** (`alpha-zero-engine/finance/native.py`):
   `native_advisor(kind, character, situation, question)` → Go command, unwraps
   `{status, backend, result}` envelope, Python fallback under `OLLAMA_DISABLE=1`.
5. **Parity tests** (`alpha-zero-engine/tests/test_native_core.py`): 21 new
   tests, all passing. Full `test_native_core.py`: 38 passed / 2 skipped (TiDB).
   Engine suite: 48 passed / 5 skipped. `test_ai_integration.py` +
   `test_monitoring.py`: 25 passed / 17 skipped. Go build via
   `core/scripts/build_core.sh` OK.
6. **Mentor note**: Go `life_coach` block is an explicit baseline (message
   "baseline life coaching from Go core..."); the full `LifeCoachAgent` stays
   Python-only and the Rust client bridges to it. Mentor parity tests exclude
   the `life_coach` key by design.
7. **MCP tool call fix**: the MCP framework passes `character_json` as a
   parsed dict (not a string), so `mcp_server.py` now has `_parse_character()`
   that accepts JSON string OR dict; applied to the 3 advisor handlers AND the
   pre-existing `alpha_zero_coach` handler.
8. **Web-server MCP deployed**: `alpha-zero-engine/mcp_server.py` runs on the
   web server (this machine, 178.104.71.88) as systemd unit
   `alpha-zero-mcp.service` → Streamable HTTP at `http://127.0.0.1:8020/mcp`
   (unit file committed at `deploy/systemd/alpha-zero-mcp.service`). Verified:
   24 alpha_zero_* tools listed incl. the 3 new advisors, and end-to-end
   `tools/call` returns real advice (`isError:false`). Restart with
   `systemctl restart alpha-zero-mcp`. The engine MCP uses the file-based
   `cmb.py` store (repo `alpha-zero-engine/cmb_data/`) — no CMB server needed.

## Current git state (as of handoff)
- Repo: `/home/alieninc/alphazero` (server, 178.104.71.88, host `alieninc`).
  Remote: `origin https://github.com/thedailyartcult/alpha-zero.git`.
- Pushed to origin/main (in order): `da0f060` Phase 4, `5925d68` Phase 10
  fix, `814d253` Phase 8 advisors, `093b97a` character_json fix + systemd unit.
  Working tree CLEAN, `origin/main` in sync (verify with `git status`).
- Server toolchains: Go 1.24.11 at `/home/alieninc/toolchains/go/bin`
  (`export PATH=/home/alieninc/toolchains/go/bin:$PATH`), Rust at
  `/home/alieninc/toolchains/rustup` + `/home/alieninc/toolchains/cargo`
  (`export PATH=$CARGO_HOME/bin:$PATH`).
- Working tree should be CLEAN after the push (verify with `git status`).
- TOPOLOGY: the "laptop" (host `tablet`, IP 136.239.224.38) is the developer's
  local machine and holds the canonical CMB DB. It maintains SSH sessions into
  this server (as root) and a reverse tunnel: this server's `127.0.0.1:8766`
  (an sshd) forwards to the laptop's CMB MCP. The laptop's repo copy lives at
  `/home/tablet/alieninc/alphazero`. The laptop does NOT accept inbound SSH from
  the server (port 22 filtered), so git pulls on the laptop must be run from the
  laptop itself.

## What is NEXT (open threads)
1. **Laptop sync**: On the laptop run
   `cd /home/tablet/alieninc/alphazero && git fetch origin && git pull --ff-only`
   (or the laptop's `sync-to-server.sh --pull-code` if present). Then restart
   the laptop's MCP client so `alpha_zero_financial_advisor`,
   `alpha_zero_health_coach`, `alpha_zero_mentor` appear. Confirm by listing
   tools. (The laptop, 136.239.224.38, does not accept inbound SSH from the
   server, so the pull must be run from the laptop itself.)
2. **Web-server MCP**: DONE — systemd `alpha-zero-mcp.service` on
   127.0.0.1:8020, 24 tools verified live (see What is DONE #8). Optional:
   register `http://127.0.0.1:8020/mcp` in this server's MCP client config so
   agents here can call the alpha_zero_* tools directly. Do NOT use port 8000
   (occupied by the `panteon` backend).
3. **Pre-existing failure** (NOT caused by Phase 8): fix
   `test_full_life_balance_avg_lifespan` (seed 42 multiverse avg lifespan 55.1
   < 60 assertion). Root cause uninvestigated; adjust test bound or engine.
4. **TiDB-skipped tests**: `test_report_store_load_roundtrip_go` and
   `test_report_list_go` skip because `tidb_store.healthy()` is false under
   pytest DSN defaults; verify DSN env and enable.
5. **LifeCoachAgent full Go port** (optional): to reach 100% mentor parity,
   port `ai/life_coach.py`'s deterministic core into Go so `life_coach` no
   longer needs the baseline exception.

## Build & test commands
- Go: `cd alpha-zero-engine/core/alphacore && go build -o ../bin/alphacore .`
  (or `core/scripts/build_core.sh`), then
  `python3 -m pytest tests/test_native_core.py -q`.
- Rust: `cd rust/mcp-client && export PATH=/home/alieninc/toolchains/cargo/bin:$PATH && cargo test`.
- Full Python: `cd alpha-zero-engine && OLLAMA_DISABLE=1 python3 -m pytest tests/ -q`,
  plus top-level `test_ai_integration.py` + `test_monitoring.py`.
- Determinism: always set `OLLAMA_DISABLE=1` for parity comparisons; the
  server's Ollama has 0 models.

---

END OF PROMPT — delete or rewrite this file after the next session consumes it.
