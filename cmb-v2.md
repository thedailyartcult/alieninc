# CMB MCP v2 — Refinement Plan

## Research Findings: Best MCP Servers (2026)

Based on analysis of MCP server best practices and our custom CMB MCP server:

### What Best-Practice MCP Servers Have
1. **Resource templates** — expose data as MCP resources with URI templates
2. **Prompt templates** — standardized prompt patterns for common operations
3. **Structured schemas** — full JSON Schema validation for tool parameters
4. **Streaming support** — SSE and streaming transports for large responses
5. **Multi-server composition** — separate servers for different domains
6. **OAuth 2.1 authentication** — enterprise-grade auth for HTTP transports
7. **RBAC and least-privilege** — access control per tool/resource
8. **Audit logging** — comprehensive audit trails for compliance
9. **Rate limiting** — protect against abuse and DoS
10. **Health checks** — `/health` endpoint for monitoring

### What Our CMB MCP Server Lacks
- No resource templates (memories are only accessible via tools, not resources)
- No prompt templates (no standardized recall patterns)
- No streaming support (all responses are synchronous, blocking)
- No OAuth 2.1 authentication (uses no auth on HTTP transport)
- No RBAC or least-privilege (all workspaces allowed, `allowed_workspaces: []`)
- No rate limiting (unlimited tool calls)
- No health check endpoint (monitor port is 0/disabled)
- No audit logging beyond basic `cmb_record_event`
- Injection system has low hit rates (123/189 sessions have reads, but most are short-lived)

## Our CMB MCP Server Analysis

### Current Tool Count (after P0-3 alpha_zero separation)
Core memory tools (~16):
`cmb_remember`, `cmb_recall`, `cmb_recall_context`, `cmb_recall_grounded`, `cmb_why`, `cmb_timeline`, `cmb_recall_proactive`, `cmb_proactive_context`, `cmb_forget`, `cmb_pin`, `cmb_correct`, `cmb_promote`, `cmb_link`, `cmb_record_event`, `cmb_index_repo`, `cmb_search_code`, `cmb_code_path`, `cmb_code_impact`, `cmb_export_code_graph`, `cmb_start_session`, `cmb_end_session`, `cmb_receipts`, `cmb_context_savings`, `cmb_verify_receipts`, `cmb_export_receipts`, `cmb_stats`, `cmb_check_update`, `cmb_ingest`, `cmb_ingest_postgres_schema`, `cmb_consolidate`

### Injection Stats (from logs)
- 189 total injection stat entries
- 123 sessions with file reads (65%)
- 122 sessions with hits (64.5%)
- Avg hits per session with hits: 10.5
- Avg reads per session with reads: 10.8
- Cumulative tokens saved: ~1.18M
- Cumulative injected chars: ~553M

### Key Insight: Highest Leverage Features
The features that give the highest leverage are:
1. **`cmb_recall_context`** (compact mode) — the real token-saver, must be the default
2. **`cmb_proactive_context`** — session startup context loading
3. **`cmb_consolidate`** — periodic memory maintenance reducing recall size
4. **`cmb_context_savings`** — measuring ROI of the memory system
5. **Resource templates** — exposing memories as MCP resources for direct access
6. **Prompt templates** — standardizing recall patterns for consistent results

## Sync Status
- P0-1 (sync infrastructure): Tunnel script works, SSH key generated at `/root/.ssh/cmb_sync`
- Sync from laptop: FAILING — SSH tunnel not active (tunnel process dies because laptop `authorized_keys` doesn't have the cmb_sync public key)
- Sync to laptop: No errors logged
- Public key needs laptop `authorized_keys` — fingerprint `SHA256:FwYOWLESYq0LHsMk4cwnUXXGSSmAJOZq73TsdIJOxAI`
- `sync_state` table exists in DB but is empty
- Tunnel script at `/srv/cmb/scripts/cmb-tunnel.sh` — starts tunnel on port 8766
- Sync scripts at `/srv/cmb/scripts/` — cron installed for 5-min pull, 15-min push

## MCP Server Port Fix (2026-08-06)
- **Problem**: opencode config at `/root/.config/opencode/opencode.jsonc` was pointing to `http://127.0.0.1:8766/mcp` — port 8766 is the SSH tunnel to the laptop, NOT the MCP server
- **Fix**: Changed URL to `http://127.0.0.1:8765/mcp` — port 8765 is the actual CMB MCP server (Streamable HTTP)
- The MCP server (`cmb-mcp-http`) runs on port 8765, separate from the web server (gunicorn on 8080) and the SSH tunnel (sshd on 8766)
- Both the web server and MCP server use the same codebase at `/srv/cmb/venv/` (CMB 1.2.5)
- Killed stale duplicate `/usr/local/bin/cmb-mcp-http` process
- Awaiting laptop `authorized_keys` update to enable sync

## Upgrades Needed (Priority Order)

### P0 — Critical
1. ⏳ Fix sync infrastructure — tunnel script works, SSH key generated, but laptop `authorized_keys` needs cmb_sync public key (SHA256:FwYOWLESYq0LHsMk4cwnUXXGSSmAJOZq73TsdIJOxAI). **Requires laptop access to add key.**
2. ✅ Add resource templates — 7 templates implemented (`cmb://memories/{workspace}`, `cmb://memory/{workspace}/{repo}/{session}`, `cmb://workspace/{workspace}`, `cmb://savings`, `cmb://sessions`, `cmb://graph/{workspace}`, `cmb://stats`)
3. ✅ Add prompt templates — 4 templates implemented (`context`, `handoff`, `consolidation`, `quality-audit`)
4. ✅ Add health check endpoint — enabled via `CMB_MONITOR_PORT` (default 8767), serves `/health` and `/metrics`

### P1 — Important
5. Add streaming support — SSE transport for large memory recalls
6. Add OAuth 2.1 authentication — replace no-auth HTTP transport
7. Add RBAC and least-privilege — configure `allowed_workspaces` properly
8. Add rate limiting — protect against abuse
9. Add structured schema validation for tool parameters
10. Fix injection system hit rates — improve memory relevance scoring

### P2 — Nice to Have
11. Add audit logging — comprehensive audit trails
12. Add multi-server composition support — dynamic MCP server discovery
13. Add `cmb_migrate` tool — migrate memories between instances
14. Add `cmb_sync_status` tool — report sync health

## Next LLM Query

Use this query on the next LLM session to continue the CMB v2 refinement:

```
Query the CMB memory for the CMB v2 refinement plan. Use cmb_recall_context with query="CMB v2 refinement plan" and token_budget=512. If no results, check cmb_recall with query="CMB v2" and k=5. Report: (1) current CMB version, (2) which P0/P1/P2 upgrades are done, (3) which are pending, (4) sync status between server and laptop, (5) highest leverage features identified, (6) what the next LLM should focus on. If the cmb-v2.md file at /home/alieninc/cmb-v2.md exists, read it and summarize the pending items.
```

### Short Version
```
CMB v2: cmb_recall_context(query="CMB v2 refinement plan", token_budget=256). If empty, read /home/alieninc/cmb-v2.md and report pending P0 items and sync status.
```

### Ultra-Short Version
```
CMB v2: cmb_recall_context("CMB v2", budget=128). Report pending P0 only.
```

## File Location
This document is at `/home/alieninc/cmb-v2.md` and should be stored in CMB memory for queryability.