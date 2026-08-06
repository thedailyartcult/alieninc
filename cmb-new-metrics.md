# CMB New Metrics — Action Plan & Tracking

**Workspace:** `alieninc` (shared, laptop + server)
**Repo:** `cmb`
**Canonical source:** `/root/cmb-upgrade/src/cmb` (server) / `/home/tablet/cmb-upgrade/src/cmb` (laptop)
**Build/deploy:** `/root/cmb-upgrade/upgrade-cmb.sh` (rebuild + restart `cmb-mcp-http.service`)
**Live DB:** `/srv/cmb/data/cmb.db`
**Started:** 2026-08-06

## Status Legend
- [ ] not started
- [x] done
- [ ] 🔶 in progress / partial
## How to resume this work (MANDATORY read first)
If you are another LLM picking this up, do NOT re-diagnose or re-initiate anything below.
Load the CMB tracking memory with the recall query:

    cmb_recall_context(query="CMB new metrics roadmap action plan status and phase completions",
                       workspace="alieninc", token_budget=512, k=8)

Then `cmb_recall_proactive(workspace='alieninc', repo='cmb', k=5)` for the latest session handoff,
and check this file's Status section (authoritative). Baseline metrics are in
`mem_01KZANW3J7XZGENMR740YRTWC2` (recall `cmb_recall(query="CMB token-savings review")`).

## Baseline (measured 2026-08-06, workspace `alphazero` — the only one with usage data)
- 23 recall receipts carry `token_usage`.
- source_tokens = 52,669 · context_tokens = 16,886 · **saved_tokens = 35,813** · **savings_ratio = 68.0%**
- By response_mode: **compact 81.1%** (16 receipts, saved 32,750) · **full 25.0%** (7 receipts, saved 3,063)
- Counter used by packer: `cmb.regex.v1` (regex tokenizer in `cmb/core/context.py`)
- Counter used by consolidation: `estimate_tokens` (4 chars/token heuristic in `cmb/core/textutil.py`) — NOT comparable
- `alieninc` workspace only has 3 bare `remember` receipts (no token_usage yet)

## Issues found in review (2026-08-06) — status
1. 🔴 **DB permission drift** — `/srv/cmb/data/cmb.db` was chowned to `chatwoot` (mode 644) while the
   service runs as user `cmb` → every write failed `OperationalError: attempt to write a readonly database`.
   **FIXED (W1):** `ExecStartPre=/bin/chown cmb:cmb /srv/cmb/data/cmb.db` in the unit (deploy + live),
   plus `chown cmb:cmb` guard in `sync-from-laptop.sh`.
2. 🔴 **`cmb_proactive_context` always crashes** — `service.py` imports `cmb.ai_context`, but the module
   was deleted in "Phase 2: remove unused cloud/SaaS modules". Every call → `ModuleNotFoundError`.
   **FIXED (W2):** rebuilt `cmb/ai_context.py` — deterministic cited summary + suggested queries, LLM
   synthesis opt-in and accepted only when it cites `[n]` retrieved memories. Verified live.
3. 🟡 **Two token counters not comparable** — packer uses regex (`cmb.regex.v1`), consolidation/merge use
   `estimate_tokens` (char/4). Aggregating both in `cmb_context_savings` would be apples-to-oranges.
   **FIXED (W4):** canonical `cmb.core.textutil.count_tokens` (`cmb.regex.v1`) now used by packer,
   consolidation, and merge compaction; `RegexTokenCounter` imported from textutil (single source).
4. 🟡 **`full` response_mode `saved_tokens` misleading** — mostly `0`, looks like "no savings", but it just
   means no omission happened. Add `omitted_tokens` to distinguish dropped candidates from truncation.
   **FIXED (W5):** `ContextUsage.omitted_tokens` sums source tokens of un-packed candidates; persisted in
   receipts and aggregated in `cmb_context_savings`. Full mode → 0, compact → real count.
5. 🟡 **Consolidation never scheduled/run** — jobs table empty, no consolidate in audit. Untapped lever.
   **FIXED (W3):** nightly cron `30 2 * * *` → `/srv/cmb/scripts/consolidate-sweep.sh` (as `cmb` user);
   `consolidate` receipts now carry `token_usage` (service + CLI paths, `cmb.regex.v1`).
6. 🟢 **Compact default budget 1024 is tight** — 81% savings shows headroom; raising improves evidence density.
   **DONE (W6):** `cmb_recall_context` default `token_budget` 1024 → 2048.

## Workstream / status
| # | Task | File(s) | Status |
|---|------|---------|--------|
| W1 | Permanent DB owner guard (systemd ExecStartPre + sync scripts chown) | `/home/alieninc/deploy/cmb-mcp-http.service`, `/srv/cmb/scripts/sync-*.sh` | [x] done |
| W2 | Rebuild `cmb.ai_context` (deterministic proactive-context builder) | `/root/cmb-upgrade/src/cmb/ai_context.py` (new) | [x] done |
| W3 | Schedule consolidation (cron) + record consolidation token_usage in receipts | `/srv/cmb/scripts/cmb-sync-cron`, `scripts/consolidate.py`, `service.py` | [x] done |
| W4 | Unify counters → consolidation uses `cmb.regex.v1` | `cmb/core/consolidate.py`, `cmb/core/engine.py`, `cmb/core/textutil.py`, `cmb/core/context.py` | [x] done |
| W5 | Add `omitted_tokens` to `ContextUsage` for honest full-mode accounting | `cmb/core/context.py`, `cmb/core/interfaces.py`, `cmb/core/store.py` | [x] done |
| W6 | Raise `cmb_recall_context` default token_budget 1024 → 2048 | `cmb/mcp_server.py` | [x] done |
| W7 | Rebuild via `upgrade-cmb.sh`, restart, verify all tools | — | [x] done |
| W8 | Update this file + CMB tracking memory | this file, CMB | [x] done |

## Completion log (append-only — never re-do completed items)
- **2026-08-06** Review delivered; baseline metrics captured; DB permission fixed manually (`chown cmb:cmb`);
  `cmb_new_metrics` plan created and stored in CMB.
- **2026-08-06** All W1–W8 implemented, rebuilt (`upgrade-cmb.sh`), service restarted, verified live:
  `cmb_proactive_context` now returns cited summaries (was `ModuleNotFoundError`); `cmb_context_savings`
  reports `omitted_tokens`; counters unified on `cmb.regex.v1`; nightly consolidation cron at `30 2 * * *`
  (`/srv/cmb/scripts/consolidate-sweep.sh`) records `consolidate` token_usage receipts; ExecStartPre chown
  guard in `/etc/systemd/system/cmb-mcp-http.service` (deploy copy updated too). Verified with MCP tools
  against the live server (PID 3107661). To push code changes to the laptop: `/home/tablet/sync-to-server.sh --pull-server`
  from the laptop side pulls installed `cmb/` + `scripts/` — **note**: new `cmb/ai_context.py` must also be
  copied (only `cmb/` + `scripts/` are tarred, which includes it).
