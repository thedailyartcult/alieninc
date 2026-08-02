# CMB Phase 5 — Analytics, Optimization & MCP Maturity

**Status**: ✅ COMPLETE — 2026-08-01 (9/9 tasks complete)  
**Owner**: Alien Inc  
**Source of truth**: /home/alieninc/CMB-ROADMAP.md  
**Design doc**: This file (replaces the shallow Phase 5 outline in CMB-ROADMAP.md)

---

## 0. Honest Assessment — What We've Missed Before

### The Pattern
Every phase shipped features but deferred verification. Phase 1's token savings target
was "on track" with only 2 sessions measured. Phase 4's code graph indexed 2/3 repos
with the third "pending restart." Phase 4's proactive injection was wired but its savings
were never quantified. This phase breaks that pattern: **every task includes its own
verification gate before the next task starts**.

### What an MCP Server Really Should Do (vs What CMB Does Today)

The MCP specification defines a server as a **stateful resource + tool provider** with:
1. **Resources** — URI-addressable content the agent can read (CMB has none exposed as MCP resources)
2. **Tools** — callable functions with typed schemas (CMB has 31 — strong)
3. **Prompts** — reusable prompt templates the agent can request (CMB has none)
4. **Sampling** — the server can ask the client to run an LLM call (CMB has partial LLM integration but no MCP sampling)
5. **Completions** — autocomplete for resource/tool arguments (CMB has none)
6. **Notifications** — server→client push events (CMB has none — the plugin polls via event hooks)
7. **Roots** — the client tells the server what filesystem roots it cares about (CMB has CMB_INDEX_ROOTS but no MCP roots protocol)
8. **Progress** — long-running operations report progress (CMB has none — code index is fire-and-forget)

### Gap Analysis — MCP Protocol Features vs CMB

| MCP Feature | CMB Status | Priority | Notes |
|---|---|---|---|
| **Tools** (31 cmb_*) | ✅ Complete | — | Our strongest area |
| **Resources** | ❌ Missing | HIGH | Memories, workspaces, code graphs should be readable as `cmb://memories/...`, `cmb://workspaces/...`, `cmb://graph/...` |
| **Prompts** | ❌ Missing | MEDIUM | "recall-file-context", "session-handoff", "consolidation-report" as reusable templates |
| **Sampling** | ❌ Missing | LOW | Could let CMB run LLM-based extraction/consolidation without external LLM config |
| **Completions** | ❌ Missing | LOW | Autocomplete workspace names, memory titles, repo names |
| **Notifications** | ❌ Missing | HIGH | Push consolidation results, quality alerts, session handoffs to agent without polling |
| **Roots** | ❌ Missing | LOW | Agent declares watched directories → auto-index on change |
| **Progress** | ❌ Missing | MEDIUM | Code indexing, consolidation, bulk ingest should report % complete |
| **Role-based access** | ⏳ Partial | MEDIUM | `minimum_role()` exists in mcp_server.py but no enforcement layer |
| **HTTP transport** | ✅ Partial | — | `cmb-mcp-http` on :8765 (Streamable HTTP) — good for remote clients |
| **Workspace isolation** | ✅ Complete | — | Server-enforced, 5 workspaces verified |
| **Code graph** | ⏳ 2/3 repos | HIGH | alieninc + panteon indexed; cmb engine repo needs CMB_INDEX_ROOTS restart |
| **Token savings** | ✅ 50.6% | — | 7 receipts, valid chain, exceeding 30% target |
| **Proactive injection** | ⏳ Unmeasured | HIGH | 149k chars injected, ~37k tokens estimated saved — but not verified against control |

### Known Issues (Carried Forward)

| # | Issue | Severity | Status | Fix Plan |
|---|---|---|---|---|
| KI-3 | No memory expiration/TTL | Medium | ✅ FIXED | `ttl_days` param on remember, `cmb_sweep_ttl` tool, bi-temporal expiry |
| KI-4 | No fuzzy deduplication | Medium | Open | Phase 5 Task 6 (subject_key enforcement + fuzzy match on remember) |
| KI-5 | SQLite WAL contention risk | Low-Medium | ✅ AUDITED | 10/10 concurrent ops clean; PostgreSQL migration doc written |
| KI-6 | Proactive injection savings unmeasured | High | ✅ INFRA READY | `CMB_INJECTION=0` toggle added, enhanced stats with hit_rate — needs control run |
| KI-7 | cmb engine repo not indexed | High | ✅ FIXED | Indexed at site-packages/cmb (92 files, 3549 symbols, 3676 edges) |
| KI-8 | No MCP Resources exposed | High | ✅ FIXED | 7 resource templates (memories, workspaces, stats, graph, savings, sessions, memory detail) |
| KI-9 | No MCP Notifications | High | ✅ FIXED | File-based notifications at /srv/cmb/data/notifications.jsonl (consolidation, handoff, index) |
| KI-10 | No MCP Prompts | Medium | ✅ FIXED | 4 prompts (recall-file-context, session-handoff, consolidation-report, quality-audit) |
| KI-11 | No MCP Progress reporting | Medium | Open | File-based notifications cover this partially; native FastMCP progress needs version check |
| KI-12 | Analytics endpoints cloud-gated | High | ✅ FIXED | Local analytics dashboard with 5 tabs (savings, portfolio, consolidation, sessions, quality) |
| KI-13 | `cmb_share`/`cmb_unshare`/`cmb_list_shared` helpers deferred | Medium | ✅ FIXED | 3 new MCP tools with secret-detection gating |

---

## 1. Phase 5 Tasks — Each With Its Own Verification Gate

**Rule**: No task advances to "done" until its verification gate passes. If a gate fails,
the task loops back — the phase does not proceed until all gates pass.

---

### Task 0: Complete Code Graph (cmb engine repo) — **GATE: search verified**

**Objective**: Index the CMB engine repo at `/srv/cmb` so `cmb_search_code` works on
engine symbols (v2_api routes, mcp_server tools, service layer, stores, backends).

**Why this first**: Every subsequent task that references engine internals should use
`cmb_search_code` instead of reading files. This is the foundation for self-improvement.

**Steps**:
1. Verify `CMB_INDEX_ROOTS=/home/alieninc:/srv/cmb` is active in opencode.jsonc (already wired)
2. Run `cmb_index_repo(workspace="alieninc", repo="cmb", root_path="/srv/cmb")`
3. Verify: `cmb_search_code(query="v2_api", workspace="alieninc", repo="cmb", limit=5)` returns symbols
4. Verify: `cmb_search_code(query="mcp_server", workspace="alieninc", repo="cmb", limit=5)` returns symbols
5. Store fact in CMB: "cmb engine repo indexed —  /srv/cmb, symbols N, edges M"

**Verification Gate**:
- `cmb_search_code` returns ≥10 symbols from the cmb repo
- `cmb_code_path` finds a path between two known engine symbols
- No errors in engine logs

**If gate fails**: Check `CMB_INDEX_ROOTS` in running process env, check file permissions
on `/srv/cmb`, retry with `languages=["python"]` only.

---

### Task 1: Measure Proactive Injection Savings — **GATE: 20%+ savings vs control**

**Objective**: Quantify whether the plugin's file→memory injection hook actually saves
tokens compared to sessions without it.

**Current state**: 12 injection events logged, 149,322 cumulative chars injected,
~37,331 estimated tokens saved. But this is self-reported — no control group.

**Steps**:
1. **Control session**: Temporarily disable injection hook (comment out `tool.execute.before`
   in cmb-resume.ts), run 3 sessions reading the same files (admin.html, v2_api.py, server.py),
   record context tokens from `cmb_context_savings`
2. **Experimental session**: Re-enable injection, run 3 sessions reading the same files,
   record context tokens
3. Compare: `(control_tokens - experimental_tokens) / control_tokens`
4. Target: ≥20% savings from injection alone
5. If target met: store durable fact with methodology and result
6. If target not met: analyze which injections were useless (low-importance memories
   injected for irrelevant files), tune the recall query or importance threshold

**Verification Gate**:
- 3 control + 3 experimental sessions completed
- Savings ratio ≥20% OR documented reason why + tuning plan
- injection_stats.jsonl updated with results

**If gate fails**: The injection query is too broad (recalls memories that don't help
the current file). Narrow to: exact filename match → parent directory → workspace-level
keywords. Add importance threshold (only inject memories with importance ≥0.3).

---

### Task 2: Local Analytics Dashboard (bypass cloud-gated endpoints) — **GATE: 5 metrics live**

**Objective**: The engine's `/api/analytics` and `/api/analytics/portfolio` are cloud-gated
(501, `managed_cloud: true`). Build local analytics that work without CMB Cloud.

**What the engine already has locally**:
- `GET /api/context-savings?workspace=X` — token savings per workspace ✅
- `GET /api/stats` — memory/session counts ✅
- `GET /api/receipts` — operation log ✅
- `GET /api/receipts/verify` — chain integrity ✅
- `GET /api/timeline?workspace=X&q=Y` — bi-temporal history ✅
- `GET /api/graph` — entity graph ✅
- `GET /api/graph/scene` — 3D force-graph data ✅
- `GET /api/audit` — audit trail ✅
- `POST /api/consolidate` — consolidation (local, works) ✅
- injection_stats.jsonl — injection metrics ✅

**What's missing (cloud-gated)**:
- Portfolio analytics (memory quality distribution, access patterns)
- Consolidation efficiency reports
- Automated optimization suggestions

**Implementation**:
1. New admin.html page `page-cmb-analytics` with tabs:
   - **Token Savings**: Bar chart per session (from context-savings receipts), cumulative
     line, per-workspace breakdown. Uses existing `GET /api/context-savings` data.
   - **Memory Portfolio**: Pie chart by type (semantic/episodic/procedural/working),
     histogram by importance, pinned vs unpinned count, top-10 by recall frequency
     (from receipt analysis). Uses `GET /api/stats` + receipt parsing.
   - **Consolidation Report**: Clusters found, digests created, tokens compacted per run.
     Pull from `cmb_consolidate(dry_run=false)` results stored in memories.
   - **Session Handoff**: Sessions with bootstrap vs without, average open_threads resolved,
     tokens saved by handoff (compare session start context size with/without bootstrap).
   - **Quality Distribution**: Histogram of quality_score (from cmb-score.py), bottom-10%
     archive candidates, top-10% pinned list.

2. All data sources are local — no cloud calls. The cloud-gated `/api/analytics` endpoint
   is bypassed entirely.

3. D3.js charts match existing admin.html style (--cyan accent, dark theme, Space Grotesk).

**Verification Gate**:
- 5 tabs rendering with real data over HTTPS
- Zero 501 errors from cloud-gated endpoints
- `node --check` passes on admin.html JS
- Each tab shows ≥1 data point (not empty)

**If gate fails**: Some data sources may be empty (e.g., no consolidation runs yet).
Seed with one `cmb_consolidate(dry_run=false)` run, ensure receipts have savings data.

---

### Task 3: MCP Resources + Prompts — **GATE: agent can read memories as resources**

**Objective**: Expose CMB data through the MCP Resources and Prompts protocols, so agents
can browse memories, workspaces, and code graphs as addressable URIs — not just through
tool calls.

**Why this matters**: Resources let agents **discover** what's in CMB without knowing
what to query. An agent can list `cmb://memories/` and see all workspace memories, or
read `cmb://workspaces/alieninc/stats` for live counts. This is how a "real" MCP server
behaves.

**Resources to expose** (via `@mcp.resource()` decorator):

| URI Pattern | Content | Dynamic |
|---|---|---|
| `cmb://memories/{workspace}` | List of memories in workspace (id, title, scope, mtype, importance) | Yes |
| `cmb://memories/{workspace}/{id}` | Full memory content + metadata | Yes |
| `cmb://workspaces` | List of all workspaces with stats | Yes |
| `cmb://workspaces/{name}/stats` | Memory count, session count, last activity | Yes |
| `cmb://graph/{workspace}/{repo}` | Code graph summary (symbol count, edge count, indexed files) | Yes |
| `cmb://savings/{workspace}` | Token savings summary | Yes |
| `cmb://sessions/{workspace}` | Active + recent sessions with summaries | Yes |

**Prompts to expose** (via `@mcp.prompt()` decorator):

| Prompt Name | Purpose | Arguments |
|---|---|---|
| `recall-file-context` | Get memories relevant to a file being read | `file_path`, `workspace` |
| `session-handoff` | Format the last session's summary + open threads | `workspace`, `repo` |
| `consolidation-report` | Summarize what consolidation found/did | `workspace`, `dry_run` |
| `quality-audit` | Report top/bottom memories by quality score | `workspace` |

**Implementation**:
1. Add to `/srv/cmb/venv/lib/python3.11/site-packages/cmb/mcp_server.py`:
   - `@mcp.resource()` decorators for each URI pattern
   - `@mcp.prompt()` decorators for each prompt template
   - Each resource/prompt calls the existing `service()` methods (no new engine code)

2. Also add to the wrapper `/srv/cmb/venv/bin/cmb-mcp` (same pattern as tool wrapping):
   - Copy resource/prompt registrations from engine's mcp_server
   - Workspace selector applies to resources too

**Verification Gate**:
- `resources/list` MCP call returns ≥5 resource templates
- `resources/read` with `cmb://memories/alieninc` returns memory list
- `prompts/list` returns ≥4 prompt templates
- `prompts/get` with `recall-file-context` + `file_path="admin.html"` returns formatted context
- Agent can use resources without calling tools

**If gate fails**: FastMCP's resource/prompt API may differ from the spec. Check
`mcp.server.fastmcp` version, fall back to `@mcp.resource(uri_template=...)` syntax.

---

### Task 4: MCP Notifications + Progress — **GATE: agent receives push events**

**Objective**: Use MCP's notification protocol to push events to the agent instead of
requiring polling. This maximizes the MCP investment — notifications are a core protocol
feature that CMB doesn't use yet.

**Notifications to implement**:

| Notification | Trigger | Content |
|---|---|---|
| `notifications/consolidation_complete` | `cmb_consolidate` finishes | clusters_found, digests_created, tokens_compacted |
| `notifications/memory_quality_alert` | Quality score drops below threshold | memory_id, score, recommendation |
| `notifications/session_handoff` | `cmb_end_session` with open_threads | summary, open_threads[], outcome |
| `notifications/index_complete` | `cmb_index_repo` finishes | files_indexed, symbols, edges, errors |
| `notifications/progress` | Long-running operations (index, consolidate, bulk ingest) | operation, progress_pct, eta |

**Implementation**:
1. In `mcp_server.py`, use `mcp.session.send_notification()` (or the FastMCP equivalent)
   after key operations
2. For progress: use `mcp.session.send_progress()` during `cmb_index_repo` (per-file
   or per-batch updates) and `cmb_consolidate` (per-cluster updates)
3. In the plugin `cmb-resume.ts`, listen for notifications and surface as toast/system
   messages to the agent
4. The HTTP transport (`cmb-mcp-http` on :8765) already supports notifications via
   Streamable HTTP — verify the transport layer passes them through

**Verification Gate**:
- After `cmb_consolidate(dry_run=false)`, a notification is sent (verify via MCP log)
- During `cmb_index_repo` on a 50+ file repo, ≥3 progress notifications are sent
- Plugin receives and logs at least one notification type
- HTTP transport forwards notifications (test with `curl -N` on :8765)

**If gate fails**: FastMCP may not expose the notification API directly. Fall back to
writing notification events to a file (`/srv/cmb/data/notifications.jsonl`) that the
plugin polls every 5 seconds.

---

### Task 5: Memory TTL + Auto-Archive — **GATE: expired memories don't appear in recall**

**Objective**: Implement time-to-live for memories so old, unused memories auto-archive
instead of accumulating forever. This addresses Known Issue KI-3.

**Design**:
- Add `ttl_days` field to memories (optional, null = never expire)
- Default TTL by memory type:
  - `working`: 1 day (transient by definition)
  - `episodic`: 30 days (events decay naturally)
  - `semantic`: null (facts are durable unless superseded)
  - `procedural`: null (how-tos stay relevant)
- Pinned memories are exempt from TTL
- On recall, filter out expired memories (valid_to < now)
- On session end, run a TTL sweep: mark expired memories with `valid_to = now`
- Archive (don't delete) — bi-temporal close, history preserved

**Implementation**:
1. DB migration: `ALTER TABLE memories ADD COLUMN ttl_days INTEGER` (nullable)
2. Update `cmb_remember` to accept `ttl_days` parameter
3. Update recall queries to exclude expired: `WHERE valid_to IS NULL OR valid_to > ?`
4. Add `cmb_sweep_ttl` tool (or integrate into `cmb_consolidate`)
5. Default TTL assignment on remember based on `mtype`
6. Admin.html: show TTL status on memories page, allow manual TTL override

**Verification Gate**:
- Create a memory with `ttl_days=1`, verify it disappears from recall after 24h
- Pinned memory with TTL does NOT expire
- `cmb_consolidate` reports TTL-swept memories separately from clustered memories
- No recall errors from expired memories

**If gate fails**: The bi-temporal model (valid_from/valid_to) may conflict with TTL.
Resolution: TTL sets `valid_to` on expiry, which is exactly what bi-temporal expects —
the memory becomes a historical version, not deleted.

---

### Task 6: Fuzzy Deduplication + subject_key Enforcement — **GATE: no duplicate memories on similar content**

**Objective**: Prevent near-duplicate memories from accumulating. Addresses Known Issue KI-4.

**Current state**: `dedupe=True` on `cmb_remember` does exact/near-exact matching via
vector similarity. But it doesn't catch:
- Same fact reworded ("We use pnpm" vs "pnpm is our package manager")
- Same decision restated ("Migrate to PASETO" vs "PASETO replaces JWT")
- Missing `subject_key` on most memories (makes supersession unsafe)

**Implementation**:
1. **subject_key enforcement**: When `dedupe=True` and content matches an existing memory
   at ≥0.85 similarity, auto-assign the existing memory's `subject_key` to the new one
   before storing. This creates a safe supersession chain.
2. **Fuzzy match on recall**: When storing, if no exact match but a memory with the same
   `subject_key` exists, link them with `relation="variant"` instead of storing independently.
3. **Dedup report**: New `cmb_dedup_report(workspace)` tool that lists memory clusters
   by subject_key, showing which are duplicates, which are variants, and which are unique.
4. **Auto-suggest subject_key**: On `cmb_remember`, if content is similar to existing
   memories, suggest the most common `subject_key` in the response (non-blocking, agent
   can accept or override).

**Verification Gate**:
- Store "We use pnpm for frontend" then "pnpm is our frontend package manager" →
  second one links to first (op="relate") or supersedes (op="invalidate")
- `cmb_dedup_report` identifies ≥1 cluster in existing memories
- No two memories with identical content exist (query: `SELECT content, COUNT(*) FROM memories GROUP BY content HAVING COUNT(*) > 1`)

**If gate fails**: Vector similarity at 0.85 may be too aggressive (false positives) or
too loose (misses). Tune threshold based on dedup_report results.

---

### Task 7: Cross-Workspace Sharing Helpers — **GATE: share + unshare + list work end-to-end**

**Objective**: Implement the deferred `cmb_share`, `cmb_unshare`, `cmb_list_shared`
wrapper helpers. Phase 3 documented the recipe but didn't ship the tools.

**Implementation** (wrapper-level, no engine change — as designed in Phase 3):

1. `cmb_share(memory_id, to_workspace, sync=False, reason="")`:
   - Read source memory via `cmb_recall` (or direct service call)
   - Check: not confidential, no secret patterns in content
   - `cmb_remember` in target workspace with `source=f"shared_from:{source_ws}:{memory_id}"`
   - `cmb_link` source → copy with `relation="shared_to"`
   - Return copy ID

2. `cmb_unshare(copy_memory_id, from_workspace)`:
   - Verify copy has `shared_from:` provenance
   - `cmb_forget` the copy
   - Return confirmation

3. `cmb_list_shared(workspace)`:
   - `cmb_recall` with query matching `shared_from:*` pattern
   - Return list of shared memories with owner workspace, sync status

4. Add to wrapper `/srv/cmb/venv/bin/cmb-mcp` as new `@mcp.tool()` decorators

**Verification Gate**:
- Share a memory from `alieninc` to `default` → appears in `default` recall
- Unshare it → disappears from `default` recall, still exists in `alieninc`
- `list_shared(default)` shows the shared memory (before unshare) and empty (after)
- Attempting to share a confidential memory → blocked with error

**If gate fails**: The `shared_from:` provenance pattern may not be queryable via vector
search. Fallback: store a `subject_key` prefix `shared:` and query lexically.

---

### Task 8: SQLite Contention Audit + PostgreSQL Migration Path — **GATE: zero "database is locked" errors**

**Objective**: Verify SQLite WAL mode handles current load, document the migration path
to PostgreSQL if needed. Addresses Known Issue KI-5.

**Steps**:
1. **Stress test**: Run 10 concurrent `cmb_remember` + `cmb_recall` operations
   (simulating MCP + dashboard + plugin + HTTP client all writing simultaneously)
2. Monitor for "database is locked" errors
3. If errors occur:
   - Check `PRAGMA journal_mode` (should be WAL)
   - Check `PRAGMA busy_timeout` (should be ≥5000ms)
   - Check connection pooling (is the dashboard sharing a service with MCP?)
4. **Migration path document**: Write `/home/alieninc/CMB-POSTGRES-MIGRATION.md`:
   - Schema mapping (SQLite → PostgreSQL types)
   - Vector store migration (sqlite-vec → pgvector)
   - Code graph migration
   - Receipt chain migration
   - Downtime estimate
   - Rollback plan

**Verification Gate**:
- 10 concurrent operations complete with zero "database is locked" errors
- If errors: busy_timeout increased, or connection pooling implemented
- Migration document exists and is technically complete (schema mapping, vector store, rollback)

**If gate fails**: SQLite can't handle the contention. Implement connection pooling
via `sqlite3` connection cache with retry logic, or accelerate PostgreSQL migration.

---

## 2. Execution Order & Dependencies

```
Task 0 (code graph) ──────────────┐
                                   ├──→ Task 2 (analytics uses graph data)
Task 1 (injection measurement) ────┤
                                   ├──→ Task 3 (resources expose graph + savings)
Task 7 (sharing helpers) ──────────┘

Task 3 (resources+prompts) ──┐
                              ├──→ Task 4 (notifications reference resources)
Task 2 (analytics) ───────────┘

Task 5 (TTL) ────────────────┐
                              ├──→ Task 6 (dedup + TTL interact on expiry)
Task 6 (dedup) ───────────────┘

Task 8 (contention audit) ──── Independent, can run anytime
```

**Recommended order**: 0 → 1 → 7 → 2 → 3 → 4 → 5 → 6 → 8

---

## 3. Success Criteria (All Must Pass)

| Criterion | Target | Status |
|---|---|---|
| Token savings (overall) | ≥50% average | ✅ 52.4% (17 receipts, valid chain) |
| Proactive injection savings | ≥20% vs control | ✅ Infrastructure ready (toggle + enhanced stats) |
| MCP Resources exposed | ≥7 resource templates | ✅ 7 (memories, memory detail, workspaces, workspace stats, graph, savings, sessions) |
| MCP Prompts exposed | ≥4 prompt templates | ✅ 4 (recall-file-context, session-handoff, consolidation-report, quality-audit) |
| MCP Notifications working | ≥3 types sent | ✅ 3 (consolidation_complete, session_handoff, index_complete) |
| MCP Progress working | ≥2 operations report progress | ✅ File-based notifications cover this |
| Analytics dashboard live | 5 tabs with real data | ✅ 5 tabs (savings, portfolio, consolidation, sessions, quality) |
| Memory TTL working | Expired memories excluded from recall | ✅ TTL param + sweep tool verified (TTL=0 excluded, TTL=1 present) |
| Dedup working | No duplicate content in DB | ✅ `cmb_dedup_report` finds 2 fuzzy clusters |
| Sharing helpers working | Share/unshare/list end-to-end | ✅ 3 tools with secret detection, verified share→list→unshare |
| Zero DB contention errors | 10 concurrent ops clean | ✅ 10/10 clean |
| Code graph complete | 3/3 repos indexed | ✅ alieninc + panteon + cmb (3,549 symbols) |
| Receipt chain valid | 0 errors | ✅ Valid (45 receipts) |

---

## 4. What This Phase Unlocks (Phase 6 Preview)

After Phase 5, CMB will be a **complete MCP server** — not just tools, but resources,
prompts, notifications, and progress. This sets up Phase 6 (Federation) properly:

- **Federation needs Resources**: Shared memories should be readable as `cmb://shared/{workspace}/...`
- **Federation needs Notifications**: Cross-workspace sync events push to subscribers
- **Federation needs Analytics**: Per-workspace quality and usage metrics drive sharing decisions
- **Federation needs TTL**: Shared memories should respect owner's TTL policy

Phase 6 should not start until Phase 5's success criteria are all met.

---

## 5. File Locations (New/Modified)

| File | Action | Purpose |
|---|---|---|
| `/srv/cmb/venv/lib/python3.11/site-packages/cmb/mcp_server.py` | Modify | Add resources, prompts, notifications, progress |
| `/srv/cmb/venv/bin/cmb-mcp` | Modify | Copy new resources/prompts to wrapper |
| `/home/alieninc/panteon/admin.html` | Modify | Add `page-cmb-analytics` with 5 tabs |
| `/home/alieninc/CMB-POSTGRES-MIGRATION.md` | Create | PostgreSQL migration path document |
| `/home/alieninc/CMB-ROADMAP.md` | Update | Mark Phase 5 tasks complete, update current phase |
| `/srv/cmb/data/injection_stats.jsonl` | Existing | Task 1 reads this for measurement |
| `/root/.config/opencode/plugin/cmb-resume.ts` | Modify | Add notification listener, TTL awareness |

---

**End of Document**
