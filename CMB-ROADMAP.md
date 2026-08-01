# CMB (Cosmic Microwave Background) — Strategic Roadmap

**Document Purpose**: This is the master plan for CMB, Alien Inc's proprietary MCP (Model Context Protocol) memory system. Future AI sessions should read this document first to understand the current state, goals, and next steps.

**Last Updated**: 2026-08-01  
**Current Phase**: Phase 4 (Advanced Features)  
**Owner**: Alien Inc (fully owned, no third-party dependencies)

---

## 0. Branding Policy (MANDATORY — always in force)

**CMB = Cosmic Microwave Background. It is 100% owned by Alien Inc.** The
underlying engine was purchased by Alien Inc and must be fully rebranded/migrated
as our own product. From now on:

1. **Never use "Engraphis"** (or "engraphis", "ENGRAAPHIS", etc.) anywhere in
   internal or external tooling: UI, dashboards, docs, code comments, MCP tool
   names, or user-facing output.
2. **Never reference the third-party developer** (Coding-Dev-Tools or its authors)
   in any Alien Inc internal or external material.
3. All user-facing surfaces must say **CMB** or **Cosmic Microwave Background**:
   - MCP tools: `cmb_*` (already done — wrapper renames all tools)
   - Dashboard/UI: "CMB Memory Dashboard", "CMB System Status"
   - Docs: CMB, Cosmic Microwave Background
4. The only allowed internal exception is the Python import path
   (`from engraphis import ...` in the wrapper/engine) because that is the
   installed package name — never visible to end users. Cosmetic references in
   non-user-facing engine internals should be removed over time (Phase 4+).
5. Treat the rename as a **migration**: when editing any file, grep for
   `engraphis`/`Coding-Dev` first and scrub it unless it is the import path.

> Every AI session must honor this policy. It is also stored as a pinned CMB
> memory so it survives session handoffs.

---
## 1. What is CMB?

CMB is a **Model Context Protocol (MCP) server** that provides persistent memory for AI agents. It solves the core problem of AI token waste by:

1. **Storing durable facts** (file structures, API endpoints, architectural decisions) so the AI doesn't re-read the same files every session
2. **Recalling relevant context** with a hard token budget (e.g., "give me 512 tokens about admin.html") instead of dumping entire files into context
3. **Session handoff** — compact summaries + open threads so the next session starts with context, not a 450K-token transcript

### Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  opencode (AI agent)                                         │
│  ├─ System prompt: AGENTS.md (token-saving protocol)        │
│  ├─ Plugin: cmb-resume.ts (auto-injects CMB context)        │
│  └─ MCP client → cmb-mcp wrapper (renames tools to cmb_*)   │
└────────────────────────┬────────────────────────────────────┘
                         │ stdio (JSON-RPC)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  cmb-mcp wrapper (/srv/cmb/venv/bin/cmb-mcp)                │
│  ├─ Patches 31 tools: engraphis_* → cmb_*                   │
│  ├─ Server name: cmb_mcp                                    │
│  └─ Environment: CMB_DB_PATH, CMB_API_TOKEN                 │
└────────────────────────┬────────────────────────────────────┘
                         │ Python
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  CMB Engine (systemd: cmb-engine.service)                   │
│  ├─ Loopback :8700 (no public exposure)                     │
│  ├─ Embedder: all-MiniLM-L6-v2 (384-dim vectors)            │
│  ├─ DB: /srv/cmb/data/cmb.db (SQLite WAL)                   │
│  └─ User: cmb (isolated)                                    │
└─────────────────────────────────────────────────────────────┘
```

### Current State (as of 2026-08-01)

- **Memories stored**: 22+ (admin.html, nginx, CMB deployment, stack, panteon backend API, server.py routing, ecosystem DB schema, panteon domains, roadmap plan, bug fixes, product site structure, etc.)
- **Dashboard**: Embedded in admin.html (Memory Dashboard + System Status pages)
- **Dashboard files**: `/home/alieninc/panteon/cmb/` (in-repo, version-controlled)
- **Product page**: `/home/alieninc/panteon/cmb-product.html` (Palantir-style, live)
- **Docs site**: `/home/alieninc/panteon/cmb-docs/` (6 pages: overview, API, architecture, token-savings, integration, multi-tenancy)
- **Phase 3 (multi-tenant) progress**: engine natively multi-workspace (alieninc, default, operations confirmed). Wrapper selector `CMB_DEFAULT_WORKSPACE` done + verified live + wired into opencode.jsonc. Workspaces page added to admin.html (create/rename/describe/copy/delete via native `/api/workspaces/*`) **with Token Savings card** (per-workspace `GET /api/context-savings` bars + rollup). Sharing v1 recipe in multi-tenancy.html. Design in `/home/alieninc/CMB-PHASE3-DESIGN.md`.
- **Phase 4 (advanced) progress**: consolidation automation hook installed (plugin session.idle → cmb-consolidate.py → POST /api/consolidate, throttled 30 min, all workspaces). Code graph indexed for alieninc + panteon repos (cmb_search_code live); cmb engine repo queued behind CMB_INDEX_ROOTS (next restart). Bi-temporal Timeline page live in admin.html (/api/timeline + /api/why). Remaining: proactive file→memory injection, quality scoring, 3rd repo index.
- **Nginx route**: `/panteon/cmb/` serves dashboard (old `/cmb/` route removed); `/api/` (non-v1) → CMB engine :8700
- **MCP wrapper**: `/srv/cmb/venv/bin/cmb-mcp` (patches all tool names + params + env; workspace selector)
- **Plugin**: `~/.config/opencode/plugin/cmb-resume.ts` (auto-injects context)
- **AGENTS.md**: `~/.config/opencode/AGENTS.md` (mandatory token-saving protocol)

---

## 2. Goals

### Primary Goal
**Alien Inc owns its own MCP** — not proprietary software, but a self-managed memory system for Alien Inc and its subsidiary companies. The goal is to:

1. **Save tokens** — reduce AI context bloat by 50-80% through intelligent recall
2. **Improve AI productivity** — AI starts sessions with context, not blank slate
3. **Integrate seamlessly** — CMB is a first-class product in the Panteon ecosystem
4. **Multi-tenant** — subsidiary companies get isolated workspaces with shared knowledge

### Secondary Goals
- **Public product page** — CMB gets a dedicated page like `terranean-etelogy.html`
- **Cool graphics** — memory visualization, token savings dashboard, knowledge graph
- **Federation** — cross-company memory sharing with fine-grained access control
- **Analytics** — track token savings, memory usage patterns, consolidation efficiency

---

## 3. Phased Roadmap

### Phase 1: Stabilize & Measure (Current — 2-4 weeks)

**Objective**: Verify CMB actually saves tokens, fix any bugs, establish baseline metrics.

#### Tasks

1. ✅ **Restart opencode and test the plugin**
   - Ask: "What do you know about admin.html?"
   - Expected: AI uses `cmb_recall_context` instead of reading the file
   - Verify: Check `cmb_context_savings` for token reduction

2. **Monitor token usage over 5-10 sessions** *(in progress)*
   - Run `cmb_context_savings` after each session
   - Target: 30-50% token reduction on average
   - Document: Which queries save the most tokens?

3. ✅ **Seed CMB with more durable facts** (2026-08-01: 21 memories)
   - Stored: panteon backend API structure, server.py routing, ecosystem DB schema, panteon domain modules, site serving stack, roadmap plan, bug-fix records
   - Goal: 20-30 high-value memories that prevent re-reading files — **met (21)**

4. ✅ **Fix any plugin bugs** (2026-08-01)
   - Check: Does `cmb-resume.ts` auto-inject context on session start? — **yes, active**
   - Check: Does it intercept file reads and check CMB first? — **yes (tool.execute.before)**
   - Check: Does it auto-store large outputs (>5KB) in CMB? — **yes; now restricted to `/home/alieninc/` + `/srv/cmb/` and de-duped** (Known Issue #1)
   - **NEW BUG FOUND+FIXED**: DB path mismatch — wrapper ignored `CMB_DB_PATH`, read stray DB at `/root/.local/share/engraphis/engraphis.db` while engine/dashboard/plugin used `/srv/cmb/data/cmb.db`. Fixed in wrapper (CMB_*→ENGRAPHIS_* env bridge). Requires restart.

5. ✅ **Verify MCP wrapper works** (2026-08-01)
   - Run: `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | /srv/cmb/venv/bin/cmb-mcp` (must send `initialize` handshake first)
   - Expected: All 31 tools named `cmb_*`, zero `engraphis_*` references — **verified**
   - Check: No Coding-Dev-Tools/Engraphis strings in output — **clean, incl. parameter docs** (Known Issue #2 fixed)

#### Success Criteria
- ⏳ 5+ sessions with measurable token savings (30%+ average) — **on track**: savings measured in 2 sessions so far (2026-07-31: 40.8% / 353 tokens; 2026-08-01: 66.1% / 983 tokens on admin.html recall); avg across 4 receipts is 35.2% (1336 tokens). Formal closure at 5 sessions.
- ✅ 20+ durable memories stored (21 as of 2026-08-01)
- ✅ Plugin auto-injects context without manual intervention
- ✅ Zero third-party references in MCP layer

---

### Phase 2: Product Page & Public Integration (4-8 weeks) — ✅ COMPLETE 2026-08-01

**Objective**: Create a dedicated CMB product page and integrate it into the Panteon ecosystem.

#### Tasks

1. ✅ **Create `/home/alieninc/panteon/cmb-product.html`**
   - Structure: Similar to `terranean-etelogy.html` (hero section, features, use cases, technical specs)
   - Design: Palantir-style dark theme, cyan/purple accents, Space Grotesk font
   - Content:
     - Hero: "CMB — Cosmic Microwave Background" with tagline "Persistent Memory for AI Agents"
     - Features: Token savings, session handoff, semantic search, bi-temporal history
     - Use cases: "How Alien Inc uses CMB to reduce AI token waste by 50%"
     - Technical specs: Architecture diagram, API endpoints, MCP protocol details
     - Live demo: Embedded iframe of CMB dashboard (read-only mode)

2. ✅ **Integrate into Panteon index.html**
   - Location: Products section under "Cosmos (Space)" category
   - Card: CMB icon, title, one-line description, link to `cmb-product.html`
   - Style: Match existing product cards (Terranean, YONO, Apollo, etc.)

3. ✅ **Add CMB to admin.html navigation**
   - Current: "CMB" section with "Memory Dashboard" and "System Status"
   - Add: "Product Page" link to `/panteon/cmb-product.html`
   - Add: "Documentation" link to `/panteon/cmb-docs/` (future)

4. ✅ **Create `/home/alieninc/panteon/cmb-docs/` directory**
   - `index.html` — Overview and quickstart
   - `api.html` — MCP tool reference (all 31 `cmb_*` tools)
   - `architecture.html` — Technical architecture diagram
   - `token-savings.html` — How CMB reduces tokens (with examples)
   - `integration.html` — How to integrate CMB into other AI tools

5. ✅ **Add CMB to sitemap.xml**
   - Add: `/panteon/cmb-product.html`
   - Add: `/panteon/cmb-docs/*.html`

#### Success Criteria
- ✅ Product page live at `/panteon/cmb-product.html`
- ✅ Integrated into index.html Products section
- ✅ Documentation site with 5+ pages
- ✅ Sitemap updated

---

### Phase 3: Multi-Tenant Architecture (8-12 weeks) — IN PROGRESS

**Objective**: Enable subsidiary companies to use CMB with isolated workspaces and shared knowledge.

#### Tasks

1. ✅ **Design workspace isolation model** (2026-08-01)
   - Current: Multi-workspace verified (alieninc=3, default=24, operations=2 memories; isolation server-enforced)
   - Target: Multiple workspaces (e.g., `alieninc`, `subsidiary-a`, `subsidiary-b`)
   - Isolation: Each workspace has its own memories, sessions, and receipts
   - Sharing: Curated read-only copies with `source=shared_from:<ws>:<id>` provenance; owner version wins
   - Design doc: `/home/alieninc/CMB-PHASE3-DESIGN.md`

2. ✅ **Implement workspace management UI** (2026-08-01)
   - Location: admin.html → CMB → "Workspaces" page (nav item + `page-cmb-workspaces`)
   - Features:
     - Create/rename/describe/copy/delete workspaces — native engine `POST /api/workspaces/*`
     - View workspace stats (memory count, repos, visibility)
     - Visibility toggle via `POST /api/workspaces/visibility`
   - Verified: `/api/workspaces` + `/panteon/admin.html` serve 200 over HTTPS; JS passes `node --check`

3. ✅ **Add workspace selector to MCP wrapper** (2026-08-01)
   - `cmb-mcp` now reads `CMB_DEFAULT_WORKSPACE` and injects it via `_tool_manager.call_tool`
     shim (FastMCP binds `cmb_mcp.call_tool` at construction — the manager hook is the right point)
   - Verified: `cmb_stats({})` with `CMB_DEFAULT_WORKSPACE=default` → `workspace=default`;
     explicit `{"workspace":"alieninc"}` still wins
   - Wired into opencode.jsonc `mcp.cmb.environment` (`CMB_DEFAULT_WORKSPACE=alieninc`) — active on restart

4. ✅ **Cross-workspace memory sharing — v1 recipe documented** (2026-08-01)
   - Use case: Alien Inc stores "nginx config" memory, subsidiary can read it
   - v1 recipe (in `cmb-docs/multi-tenancy.html`): curated read-only copy via `cmb_remember`
     with `metadata.shared_from='<ws>:<id>'` + `shared_sync`; revoke via `cmb_forget` on the
     copy id; owner version wins
   - `cmb_share`/`cmb_unshare`/`cmb_list_shared` wrapper helpers deliberately deferred —
     recipe works with existing tools, avoids wrapper risk

5. ✅ **Workspace analytics** (2026-08-01)
   - `cmb_context_savings` + `cmb_stats` are workspace-aware natively (`GET /api/context-savings?workspace=X`)
   - Workspaces page shows per-workspace memory counts **and** a Token Savings card with
     per-workspace bar (source → context tokens, saved, ratio) + rollup total
   - Verified: all 3 workspaces return savings data over HTTPS; admin.html JS passes `node --check`

#### Success Criteria
- ✅ 5 workspaces created: alieninc, default, operations, subsidiary-a, subsidiary-b (2026-08-01)
- ✅ Workspace isolation verified (no cross-contamination) — marker stored in subsidiary-a recalled only there, absent from alieninc
- ✅ Cross-workspace sharing recipe documented (read-only copies with provenance) — wrapper helpers deferred by choice
- ✅ Analytics dashboard shows per-workspace metrics — counts + Token Savings bar live

---

### Phase 4: Advanced Features (12-16 weeks)

**Objective**: Implement advanced CMB features for power users and complex workflows.

#### Tasks

1. ✅ **Memory consolidation automation** (2026-08-01)
   - Current: Manual `cmb_consolidate` calls
   - Target: Automatic consolidation on session end
   - Implementation: plugin `event` hook fires on `session.idle` (throttled 30 min) →
     `/root/.config/opencode/plugin/cmb-consolidate.py` POSTs `dry_run=false` to
     `POST /api/consolidate` for every workspace (reads token from opencode.jsonc,
     fail-silent). Verified: run across all 5 workspaces, idempotent (0 clusters now).
   - Goal: Reduce memory bloat by 50% (merge similar memories)

2. ⏳ **Code graph integration** *(partial — 2/3 repos indexed)*
   - Current: `cmb_index_repo` parses code into symbol graph
   - Target: Auto-index repos on first use, store graph in CMB
   - Features:
     - `cmb_code_path` — find shortest path between two symbols
     - `cmb_code_impact` — estimate blast radius of a code change
     - `cmb_search_code` — semantic code search (not just grep)
   - Use case: "What functions call `loadOverview()`?" → instant answer from CMB
   - Indexed 2026-08-01: repo `panteon` (/home/alieninc/panteon, 80 files, 1236 symbols,
     1398 edges) + repo `alieninc` (/home/alieninc, 5000 files, 49k symbols, 54k edges,
     centra/ Python engine). `cmb_search_code` verified live (ScanEngine, applyChrome).
   - ⏳ repo `cmb` (engine /srv/cmb) — requires index roots; added
     `CMB_INDEX_ROOTS=/home/alieninc:/srv/cmb` to opencode.jsonc MCP env (active on next
     restart, wrapper bridges to `ENGRAPHIS_INDEX_ROOTS`)

3. **Proactive context injection**
   - Current: Plugin injects top 6 memories on session start
   - Target: Inject context based on current task/file
   - Implementation:
     - Plugin hook `tool.execute.before` detects file being read
     - Query CMB for related memories (semantic search)
     - Inject top 3 relevant memories into system prompt
   - Goal: AI always has relevant context without asking

4. ✅ **Bi-temporal history visualization** (2026-08-01)
   - Current: `cmb_timeline` and `cmb_why` tools (text-based)
   - Target: Visual timeline in admin.html dashboard
   - Features:
     - Timeline rail — one node per version, current (valid_to=null) in cyan, superseded in amber
     - Date range per version (valid_from → valid_to), pinned/claim-kind badges
     - "Show supersession (why)" toggle → `GET /api/why` superseded-versions list
     - Workspace selector + free-text query (backend `GET /api/timeline?q=&workspace=`)
   - Verified: page serves 200, JS passes `node --check`, endpoints live (nginx/2026 timeline)
   - Use case: "What did we believe about nginx config 3 months ago?"

5. **Memory quality scoring**
   - Current: `importance` field (0-1, manual)
   - Target: Automatic quality scoring based on:
     - Access frequency (how often is this memory recalled?)
     - Token savings (how many tokens did this memory save?)
     - Freshness (how old is this memory?)
     - Conflict rate (how often is this memory corrected?)
   - Implementation: Background job updates `quality_score` field daily
   - Use case: Auto-archive low-quality memories, pin high-quality ones

#### Success Criteria
- ✅ Automatic consolidation hook installed (session.idle) — bloat reduction measurable over time
- ⏳ Code graph indexed for 3+ repos (alieninc, panteon done; cmb after restart with CMB_INDEX_ROOTS)
- ⏳ Proactive context injection saves 20%+ tokens vs manual recall (file→memory injection still partial)
- ✅ Timeline visualization live in dashboard
- ⏳ Quality scoring identifies top 10% of memories

---

### Phase 5: Analytics & Optimization (16-20 weeks)

**Objective**: Build analytics dashboards to track CMB effectiveness and optimize token savings.

#### Tasks

1. **Token savings dashboard**
   - Location: admin.html → CMB → "Analytics" page
   - Metrics:
     - Total tokens saved (cumulative)
     - Tokens saved per session (bar chart)
     - Tokens saved per memory (which memories save the most?)
     - Savings ratio (tokens saved / tokens used)
   - Data source: `cmb_context_savings` receipts
   - Visualization: D3.js charts (match existing admin.html style)

2. **Memory usage heatmap**
   - Location: admin.html → CMB → "Heatmap" page
   - Features:
     - Grid of all memories (x-axis: time, y-axis: memory title)
     - Color intensity: access frequency (darker = more accessed)
     - Click memory → show access history, token savings, related memories
   - Use case: Identify "hot" memories (pin them) vs "cold" memories (archive them)

3. **Consolidation efficiency report**
   - Location: admin.html → CMB → "Consolidation" page
   - Metrics:
     - Memories consolidated (count)
     - Tokens saved by consolidation (before vs after)
     - Consolidation ratio (memories merged / memories created)
   - Use case: Prove consolidation is working (or tune parameters)

4. **Session handoff effectiveness**
   - Location: admin.html → CMB → "Sessions" page
   - Metrics:
     - Sessions with handoff (count)
     - Tokens saved by handoff (vs resuming full transcript)
     - Open threads resolved (count)
   - Use case: Prove session handoff is better than `opencode -c`

5. **Automated optimization suggestions**
   - Implementation: Background job analyzes memory usage patterns
   - Suggestions:
     - "Memory X is accessed 50x but only saves 10 tokens — consider deleting"
     - "Memory Y is never accessed — archive it?"
     - "Memories A, B, C are similar — consolidate them?"
   - Delivery: Toast notifications in admin.html, or email digest

#### Success Criteria
- ✅ Token savings dashboard live with 5+ metrics
- ✅ Heatmap identifies top 10% of memories
- ✅ Consolidation efficiency > 50% (half the memories, same coverage)
- ✅ Session handoff saves 30%+ tokens vs full resume
- ✅ Automated suggestions implemented (at least 3 suggestion types)

---

### Phase 6: Federation & Cross-Company Sharing (20-24 weeks)

**Objective**: Enable secure memory sharing across Alien Inc subsidiaries with fine-grained access control.

#### Tasks

1. **Design federation protocol**
   - Use case: Alien Inc shares "nginx config" with subsidiary, but not "client data"
   - Protocol:
     - Memory owner marks memory as "shareable" (boolean flag)
     - Subsidiary requests access via `cmb_request_access` tool
     - Owner approves/denies via admin.html UI
     - Approved memories appear in subsidiary's CMB (read-only)
   - Security: No PII, no secrets, no client data in shared memories

2. **Implement access control lists (ACLs)**
   - Current: Memories have `scope` (session, repo, workspace, user)
   - Target: Add `acl` field (list of workspace IDs with read access)
   - Implementation:
     - `cmb_share` tool — add workspace to ACL
     - `cmb_unshare` tool — remove workspace from ACL
     - `cmb_list_shared` tool — list all shared memories
   - UI: admin.html → CMB → "Sharing" page (manage ACLs)

3. **Implement memory request workflow**
   - Use case: Subsidiary needs "nginx config" but doesn't have access
   - Workflow:
     - Subsidiary runs `cmb_request_access(memory_id, reason)`
     - Owner receives notification (email or admin.html toast)
     - Owner approves/denies via admin.html UI
     - If approved, memory appears in subsidiary's CMB (read-only)
   - Audit trail: All requests logged in `receipts` table

4. **Implement memory sync**
   - Use case: Alien Inc updates "nginx config", subsidiary needs latest version
   - Implementation:
     - Shared memories have `sync` flag (boolean)
     - If `sync=true`, updates propagate to all subsidiaries with access
     - If `sync=false`, subsidiaries keep their snapshot (no updates)
   - Conflict resolution: Owner's version always wins (no merge)

5. **Implement cross-company search**
   - Use case: Subsidiary searches "nginx" and finds Alien Inc's shared memory
   - Implementation:
     - `cmb_recall` searches local workspace + shared memories
     - Shared memories marked with `[SHARED]` prefix in results
     - Click shared memory → show owner workspace, access request button
   - Security: Shared memories are read-only, no edit/delete

#### Success Criteria
- ✅ Federation protocol designed and documented
- ✅ ACLs implemented (share/unshare/list)
- ✅ Request workflow live (request → approve → access)
- ✅ Memory sync works (updates propagate)
- ✅ Cross-company search returns shared memories

---

## 4. Technical Debt & Known Issues

### Current Issues

1. ~~**Plugin auto-store is naive**~~ ✅ **FIXED 2026-08-01**
   - Problem: `cmb-resume.ts` stored all file outputs >5KB, even if irrelevant
   - Fix: Added allow-list (`/home/alieninc/` or `/srv/cmb/`) + DB-level dedupe on title + in-session file cache

2. ~~**MCP wrapper doesn't patch tool parameters**~~ ✅ **FIXED 2026-08-01**
   - Problem: Tool descriptions mention "Engraphis" in parameter docs (7 occurrences across 6 tools)
   - Fix: `_scrub()` helper recursively rewrites `tool.parameters` (not just `tool.description`); verified zero refs in all 31 tools

3. ~~**DB path mismatch (NEW, found 2026-08-01)**~~ ✅ **FIXED**
   - Problem: opencode passed `CMB_DB_PATH` but engraphis reads `ENGRAPHIS_DB_PATH`; wrapper only copied ENGRAPHIS_*→CMB_*, so MCP layer used stray DB `/root/.local/share/engraphis/engraphis.db` while engine/dashboard/plugin used `/srv/cmb/data/cmb.db`
   - Fix: wrapper now bridges `CMB_*`→`ENGRAPHIS_*` (setdefault) before import. **Restart opencode to activate.** Orphaned stray DB can be deleted after verification.

3. **No memory expiration**
   - Problem: Old memories accumulate, bloat context
   - Fix: Add `ttl` field, auto-archive memories older than TTL

4. **No memory deduplication**
   - Problem: Similar memories stored multiple times
   - Fix: Use `subject_key` field for deduplication, or implement fuzzy matching

### Future Technical Debt

1. **SQLite WAL mode contention**
   - Risk: Multiple writers (MCP + dashboard + plugin) could cause "database is locked"
   - Mitigation: Use connection pooling, or migrate to PostgreSQL

2. **Embedding model is small**
   - Risk: `all-MiniLM-L6-v2` (384-dim) may not capture complex semantics
   - Mitigation: Upgrade to `all-mpnet-base-v2` (768-dim) if recall quality drops

3. **No memory versioning**
   - Risk: Correcting a memory loses history (old version gone)
   - Mitigation: Implement bi-temporal versioning (valid_from, valid_to)

---

## 5. How to Use This Document

### For AI Sessions

1. **Read this document first** — understand the current state and goals
2. **Check the current phase** — focus on tasks in the current phase
3. **Verify success criteria** — don't move to next phase until criteria are met
4. **Update this document** — mark tasks as complete, add new insights

### For Human Developers

1. **Review the roadmap** — understand the long-term vision
2. **Prioritize tasks** — focus on high-impact, low-effort tasks first
3. **Test thoroughly** — each phase has success criteria, verify them
4. **Document decisions** — add notes to this document for future reference

---

## 6. Appendix

### A. File Locations

- **CMB Engine**: `/srv/cmb/` (systemd: `cmb-engine.service`)
- **CMB DB**: `/srv/cmb/data/cmb.db` (SQLite WAL)
- **CMB Dashboard**: `/home/alieninc/panteon/cmb/` (in-repo)
- **CMB MCP Wrapper**: `/srv/cmb/venv/bin/cmb-mcp`
- **opencode Plugin**: `~/.config/opencode/plugin/cmb-resume.ts`
- **opencode AGENTS.md**: `~/.config/opencode/AGENTS.md`
- **opencode Config**: `~/.config/opencode/opencode.jsonc`
- **nginx Config**: `/etc/nginx/sites-enabled/alieninc`

### B. Key Commands

```bash
# Check CMB engine status
systemctl status cmb-engine

# Query CMB memories
curl -s -H "Authorization: Bearer $CMB_API_TOKEN" http://127.0.0.1:8700/api/memories?limit=10 | jq

# Check token savings
cmb_context_savings --workspace default --repo alieninc

# Restart CMB engine
systemctl restart cmb-engine

# Test MCP wrapper
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | /srv/cmb/venv/bin/cmb-mcp
```

### C. Environment Variables

```bash
CMB_DB_PATH=/srv/cmb/data/cmb.db
CMB_API_TOKEN=<from /srv/cmb/.env ENGRAPHIS_API_TOKEN>
```

### D. MCP Tools (31 total)

All tools prefixed with `cmb_`:
- `cmb_remember` — store a memory
- `cmb_recall` — retrieve memories (full bodies)
- `cmb_recall_context` — retrieve memories (packed, token-budgeted)
- `cmb_recall_grounded` — answer from memories with citations
- `cmb_recall_proactive` — get high-importance memories (no query)
- `cmb_start_session` — start a session (get bootstrap handoff)
- `cmb_end_session` — end a session (store summary + open threads)
- `cmb_forget` — retire a memory (bi-temporal close)
- `cmb_correct` — correct a memory (supersede old version)
- `cmb_pin` — pin a memory (exempt from decay)
- `cmb_link` — link two memories (A-MEM-style)
- `cmb_consolidate` — consolidate recurring memories
- `cmb_timeline` — get history of a fact (bi-temporal)
- `cmb_why` — explain why a fact is true (with supersedes)
- `cmb_context_savings` — report token savings
- `cmb_stats` — report memory counts
- `cmb_receipts` — list operation receipts
- `cmb_verify_receipts` — verify receipt chain
- `cmb_export_receipts` — export receipts
- `cmb_record_event` — log an episodic event
- `cmb_ingest` — store raw text (extract facts)
- `cmb_promote` — promote memory to wider scope
- `cmb_index_repo` — parse repo into code graph
- `cmb_search_code` — search code symbols
- `cmb_code_path` — find path between symbols
- `cmb_code_impact` — estimate impact of code change
- `cmb_export_code_graph` — export code graph
- `cmb_ingest_postgres_schema` — ingest Postgres schema
- `cmb_check_update` — check for updates (disabled)
- `cmb_answer` — backward-compatible alias for `cmb_recall_grounded`
- `cmb_proactive_context` — get proactive context packet

---

**End of Document**
