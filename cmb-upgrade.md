# CMB MCP Upgrade Plan

## Reason for Upgrade

The CMB MCP server on this web server (port 8765) and the CMB instance on the local laptop (178.104.71.88) are **separate, unsynchronized instances** with independent SQLite databases. The AGENTS.md describes an architecture where this server connects to the laptop via SSH tunnel on port 8765, but in practice:

- The CMB MCP HTTP server runs independently on this server with its own DB at `/srv/cmb/data/cmb.db`
- The laptop runs its own CMB instance with its own DB
- No sync mechanism is active between them
- The `alieninc` workspace exists on both but with different memory contents
- This means CMB recall returns different results depending on which machine you query

Additionally, the MCP server has significant bloat (48+ tools, most unrelated to memory), misleading token-savings claims, and missing sync infrastructure.

---

## Technical Findings

### Current State

| Item | Value |
|---|---|
| CMB version | 1.2.5 |
| MCP server DB | `/srv/cmb/data/cmb.db` (38 memories, 2 workspaces: `alphazero`, `alieninc`) |
| MCP tools count | ~48 (16 core memory + 15+ alpha_zero finance + 17 misc) |
| Embed model | `sentence-transformers/all-MiniLM-L6-v2` |
| Server port | 8765 (localhost only) |
| Config DB path | `/root/.local/share/cmb/cmb.db` (default, overridden by env) |
| Allowed workspaces | `[]` (none configured — all workspaces allowed) |
| Monitor port | 0 (disabled) |
| SSH tunnel | Not active — port 8765 is the CMB HTTP server, not a tunnel |

### What Actually Saves Tokens

| Tool | Token Savings | Notes |
|---|---|---|
| `cmb_recall_context` (compact mode) | **High** — returns only packed context + source IDs, not full memory bodies | This is the real token-saver. Must be used explicitly. |
| `cmb_proactive_context` | **High** — same compact approach, designed for session startup | Loads only relevant memories at session start |
| `cmb_consolidate` | **Medium** — merges similar memories, reducing total recall size | Should be run periodically, not on-demand |
| `cmb_context_savings` | **Medium** — gives hard numbers on actual savings | Useful for measuring ROI |
| `cmb_recall_proactive` | **Medium** — queryless recall of high-importance memories | Better than full `cmb_recall` |

### What Does NOT Save Tokens

| Tool | Problem |
|---|---|
| `cmb_recall` (full mode) | Returns complete memory bodies — often duplicating content. This is the default and most commonly used tool, but it returns everything. The AGENTS.md claim of "90-95% savings" only applies when `recall_context` is used consistently. |
| `cmb_ingest` / `cmb_remember` | Stores memories that then get recalled in full — storage is efficient but recall is not always. |
| `cmb_check_update` | Makes network calls (GitHub API), fails silently, fork has no upstream (`enabled:false`). |
| `cmb_ingest_postgres_schema` | Requires psycopg2 and a live PostgreSQL connection — optional dependency for a niche feature. |
| `cmb_export_code_graph` / `cmb_code_path` / `cmb_code_impact` | Code graph tools that depend on tree-sitter indexing — useful for developers but not core memory function. |
| `cmb_share` / `cmb_unshare` / `cmb_list_shared` / `cmb_request_access` | Cross-workspace sharing with ACLs — overly complex for single-user setup, adds attack surface. |
| `cmb_verify_receipts` / `cmb_export_receipts` | Receipt verification is debugging infrastructure, not a user-facing feature. |
| `cmb_sweep_ttl` | TTL expiry should be automated, not an MCP tool. |

### Alpha Zero Tools (Should Be Separated)

The following 15+ tools are portfolio/finance simulation tools from a completely separate project (`/home/alieninc/alphazero/alpha-zero-engine`). They have nothing to do with memory management and bloat the MCP server:

`alpha_zero_simulate`, `alpha_zero_scale_universes`, `alpha_zero_convergence_analysis`, `alpha_zero_compare_universes`, `alpha_zero_best_branch`, `alpha_zero_cluster_universes`, `alpha_zero_serialize_universe`, `alpha_zero_deserialize_universe`, `alpha_zero_portfolio_optimize`, `alpha_zero_financial_forecast`, `alpha_zero_risk_analysis`, `alpha_zero_compare_strategies`, `alpha_zero_recall_history`

---

## Proposed Improvements

### P0 — Critical (Fix First)

1. **Implement CMB sync between server and laptop**
   - Problem: The server and laptop have independent CMB databases. Memories stored on one are not visible on the other.
   - Solution: Set up a sync relay using the existing `cmb_sync_relay.py` or a simple SQLite WAL-based replication over SSH. The laptop should push memory changes to the server after each write, and the server should pull on a schedule.
   - Implementation: Use `cmb_record_event` to log sync operations, then a background sync script that replicates the `memories`, `workspaces`, `repos`, and `edges` tables between the two instances.
   - Sync direction: Laptop (primary) → Server (read-replica). The laptop is the canonical DB per AGENTS.md.

2. **Make `cmb_recall_context` the default recall mode**
   - Problem: `cmb_recall` (full mode) returns complete memory bodies, wasting tokens. The compact mode is the real token-saver but is not the default.
   - Solution: Change the default `response_mode` in `cmb_recall` from `"full"` to `"compact"`. Or create a `cmb_recall_compact` alias that is the default.
   - The AGENTS.md should be updated to reflect this.

3. **Remove alpha_zero finance tools from the core MCP server**
   - Problem: 15+ tools from a separate project bloat the MCP server and confuse the tool list.
   - Solution: Move these to a separate MCP server or a separate tool namespace. The core CMB MCP should only have memory management tools.

### P1 — Important

4. **Automate TTL expiry**
   - Problem: `cmb_sweep_ttl` is an MCP tool that should be a background task.
   - Solution: Add a scheduled consolidation sweep that runs automatically (e.g., via cron or a background thread in the CMB server).

5. **Fix the misleading token-savings claim**
   - Problem: AGENTS.md claims "90-95% token savings on file reads" but this only applies when `recall_context` is used consistently. Most agents default to `recall`.
   - Solution: Update AGENTS.md to clarify that savings require using `recall_context`, not `recall`. Add a `cmb_context_savings` check to the session-end workflow.

6. **Simplify cross-workspace sharing**
   - Problem: `cmb_share`/`cmb_unshare`/`cmb_list_shared`/`cmb_request_access` are overly complex for a single-user setup.
   - Solution: Either remove them or simplify to a single `cmb_share` tool with a `target_workspace` parameter.

7. **Remove `cmb_check_update`**
   - Problem: The fork has no upstream, so this tool is permanently broken. It makes network calls that can fail silently.
   - Solution: Remove the tool or make it a no-op with a clear message.

### P2 — Nice to Have

8. **Add a `cmb_recall_compact` alias**
   - Convenience tool that wraps `cmb_recall_context` with sensible defaults for the common case.

9. **Consolidate receipt tools**
   - Merge `cmb_receipts`, `cmb_verify_receipts`, `cmb_export_receipts`, and `cmb_context_savings` into one `cmb_receipts` tool with a `mode` parameter.

10. **Add sync status tool**
    - `cmb_sync_status` — reports the last sync time, sync direction, and any conflicts between server and laptop.

11. **Add a `cmb_migrate` tool**
    - Migrates memories from one workspace/repo to another, or from one CMB instance to another. Useful for the sync use case.

---

## Sync Architecture (Server ↔ Laptop)

### Current (Broken)

```
Laptop (178.104.71.88) ←— no connection —→ Server (this machine)
  CMB DB: local                          CMB DB: /srv/cmb/data/cmb.db
  Independent, unsynchronized
```

### Proposed (Fixed)

```
Laptop (178.104.71.88) —SSH tunnel—→ Server (this machine)
  CMB DB: primary (canonical)          CMB DB: read-replica (synced)
  Writes go here                       Pulls changes from laptop
                                       Pushes events to laptop
```

### Sync Implementation Plan

1. **SSH tunnel**: Establish a persistent SSH tunnel from server to laptop on a dedicated port (e.g., 8766)
2. **Sync script**: `/srv/cmb/sync-from-laptop.sh` — runs via cron every 5 minutes, pulls new/changed memories from laptop
3. **Reverse sync**: `/srv/cmb/sync-to-laptop.sh` — pushes server-local events (consolidation, TTL sweeps) back to laptop
4. **Conflict resolution**: Last-write-wins based on `updated_at` timestamp. If both sides modified the same memory, the laptop wins (primary).
5. **Sync tracking**: Use `cmb_record_event` with kind `sync` to log sync operations
6. **Sync status**: New `cmb_sync_status` tool reports last sync time, direction, and conflict count

### Sync Script Skeleton

```bash
#!/bin/bash
# /srv/cmb/sync-from-laptop.sh
# Pulls new/changed memories from laptop CMB via SSH tunnel
# Runs every 5 minutes via cron

TUNNEL_PORT=8766
LAPTOP_DB="/home/alieninc/.local/share/cmb/cmb.db"
SERVER_DB="/srv/cmb/data/cmb.db"

# Pull new memories from laptop
ssh -p $TUNNEL_PORT alieninc@178.104.71.88 \
  "sqlite3 $LAPTOP_DB \"SELECT * FROM memories WHERE updated_at > (SELECT COALESCE(MAX(synced_at), 0) FROM sync_state);\"" \
  | sqlite3 $SERVER_DB ".import /dev/stdin memories"

# Update sync state
sqlite3 $SERVER_DB "INSERT INTO sync_state (last_sync_at) VALUES (strftime('%s','now'));"
```

---

## Standard Prompt for Cross-Provider Use

Use this prompt with any opencode provider to track CMB upgrade progress. It works regardless of context window size because it's concise and structured.

```
Query the CMB memory for the CMB upgrade plan. Use cmb_recall_context with query="CMB upgrade plan" and token_budget=512. If no results, check cmb_recall with query="CMB upgrade" and k=5. Report: (1) current CMB version, (2) which P0/P1/P2 upgrades are done, (3) which are pending, (4) sync status between server and laptop. If the upgrade doc at /home/alieninc/cmb-upgrade.md exists, read it and summarize the pending items.
```

### Short Version (for small context windows)

```
Check CMB upgrade status: cmb_recall_context(query="CMB upgrade plan", token_budget=256). If empty, read /home/alieninc/cmb-upgrade.md and report pending P0 items and sync status.
```

### Ultra-Short Version (for minimal context)

```
CMB upgrade: cmb_recall_context("CMB upgrade", budget=128). Report pending P0 only.
```

---

## Progress Tracking

| Item | Status | Notes |
|---|---|---|
| P0: Implement CMB sync server↔laptop | IN PROGRESS — sync scripts created, cron installed, SSH key generated; public key needs laptop authorized_keys | Reviewed 2026-08-06 |
| P0: Make recall_context the default | DONE — changed default response_mode from "full" to "compact"; source and installed copies rebuilt | Completed 2026-08-06 |
| P0: Remove alpha_zero tools from core MCP | DONE — removed 15 alpha_zero tools; created separate alpha-zero-mcp server at /srv/cmb/alpha-zero-mcp/; CMB package rebuilt and service restarted | Completed 2026-08-06 |
| P0-v2: Add resource templates | NOT STARTED — expose memories as MCP resources with URI templates | Identified 2026-08-06 |
| P0-v2: Add prompt templates | NOT STARTED — standardized recall patterns for consistent results | Identified 2026-08-06 |
| P0-v2: Add health check endpoint | NOT STARTED — enable monitoring (currently port 0/disabled) | Identified 2026-08-06 |
| P1: Automate TTL expiry | IDENTIFIED — pending implementation | Add cron or background thread; reviewed 2026-08-06 |
| P1: Fix token-savings claim in AGENTS.md | IDENTIFIED — pending implementation | Update documentation; reviewed 2026-08-06 |
| P1: Simplify cross-workspace sharing | IDENTIFIED — pending implementation | Remove or simplify share tools; reviewed 2026-08-06 |
| P1: Remove cmb_check_update | IDENTIFIED — pending implementation | No upstream, permanently broken; reviewed 2026-08-06 |
| P2: Add cmb_recall_compact alias | IDENTIFIED — pending implementation | Convenience wrapper; reviewed 2026-08-06 |
| P2: Consolidate receipt tools | IDENTIFIED — pending implementation | Merge 4 tools into 1; reviewed 2026-08-06 |
| P2: Add cmb_sync_status tool | IDENTIFIED — pending implementation | Report sync health; reviewed 2026-08-06 |
| P2: Add cmb_migrate tool | IDENTIFIED — pending implementation | Migrate memories between instances; reviewed 2026-08-06 |

## CMB MCP v2 Refinement

A detailed v2 refinement plan has been created at `/home/alieninc/cmb-v2.md`. It includes:
- Research on best-practice MCP servers (2026)
- Analysis of our CMB MCP server gaps
- Log-based analysis of injection stats and feature usage
- Priority-ranked upgrade items (P0-v2, P1, P2)
- Next LLM query for continuing the refinement

The highest-leverage features identified are: resource templates, prompt templates, streaming support, and health check endpoint.

---

## File Location

This document is at `/home/alieninc/cmb-upgrade.md` and should be stored in CMB memory for queryability.
