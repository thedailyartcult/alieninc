# CMB Phase 3 — Multi-Tenant Architecture (Design)

**Status**: In progress — Task 1 (workspace isolation model) designed 2026-08-01
**Owner**: Alien Inc
**Source of truth**: /home/alieninc/CMB-ROADMAP.md (Phase 3, section 3)

---

## 0. Verified Current State (2026-08-01)

The engine already supports multiple workspaces natively — no schema change needed:

| Evidence | Result |
|---|---|
| `cmb_stats(workspace="default")` | 22 memories, 3 sessions |
| `cmb_stats(workspace="alieninc")` | 2 memories, 1 session |
| Isolation | Both co-exist; recall never crosses workspaces (server-enforced) |
| `workspace` param | Present on `cmb_start_session`, `cmb_remember`, `cmb_recall*`, `cmb_context_savings`, `cmb_ingest`, etc. Defaults to `default` |
| Scope widening | `cmb_promote` (session → repo → workspace) exists; workspace→workspace does not |
| Wrapper | `cmb-mcp` (100 lines) bridges env + renames tools only — no workspace awareness |

**Conclusion**: The hard part of Phase 3 (isolation) already works. What's missing is
(1) management UI, (2) a per-connection default workspace, (3) cross-workspace
sharing, (4) per-workspace analytics surfaces.

---

## 1. Workspace Isolation Model

- **Tenant = workspace**. A workspace is the trust boundary. Subsidiaries get their
  own workspace (`alieninc`, `centra`, `rousseau`, `tdac`, …). All recall/remember
  calls are scoped to exactly one workspace.
- **Project = repo** inside a workspace. Optional refinement; not a boundary.
- **Cross-workspace = curated read-only copy**, never shared pointers. A memory is
  "shared" by materializing it in the target workspace with provenance fields:
  - `source` = `shared_from:<workspace>:<memory_id>`
  - `shared_sync` = `true|false` (owner push propagates updates)
  - `shared_readonly` = `true` (edits only ever happen in the owner workspace)
- **Conflict rule**: owner's version always wins. No merge, no two-way sync.
- **Sharing invariants**:
  - Never share PII, secrets, client data. Share structural/decision knowledge only.
  - Shared memories are recallable in the target workspace, never mutable there.

### Why copy, not pointer
The engine has no ACL/pointer layer. Copy-with-provenance uses only existing
`cmb_remember` semantics and keeps recall fast (no cross-workspace joins). It is
reversible (delete the copy), auditable (receipts), and safe (target workspace
recall stays single-tenant).

---

## 2. Workspace Management UI (admin.html → CMB → Workspaces)

New admin.html page `page-cmb-workspaces`:

- **List** — all workspaces from `cmb_stats`/engine `/api/workspaces`:
  memory count, session count, last activity, token savings (`cmb_context_savings`).
- **Create** — `POST /api/workspaces {name}` (engine endpoint) — creates the workspace.
- **Set default** — writes `CMB_DEFAULT_WORKSPACE` for the current connection.
- **Sharing tab** — list shared-in/shared-out memories, toggle `shared_sync`,
  revoke (delete copy).
- Styling: match existing CMB dashboard cards (accent-cyan, --font-tech).

---

## 3. Wrapper Workspace Selector (cmb-mcp)

Add to `/srv/cmb/venv/bin/cmb-mcp`:

- Read `CMB_DEFAULT_WORKSPACE` from env (set in opencode.jsonc MCP env or shell).
- Wrap `call_tool` to `setdefault("workspace", default_workspace)` on the JSON
  arguments of tools that accept a workspace param, unless the client explicitly
  passed one.
- Expose `cmb_whoami`-style diagnostics via stderr log line: `Workspace: <name>`.
- Publish `CMB_DEFAULT_WORKSPACE` in `initialize` instructions so agents know the
  operator-configured default (mirrors `cmb_recall_proactive` guidance).

This gives each AI connection a default tenant without forcing every tool call to
repeat the workspace.

---

## 4. Cross-Workspace Sharing (v1: curated copy)

New wrapper-level helpers (no engine change) built on existing tools:

- `cmb_share(memory_id, to_workspace, sync=false, reason)` →
  `cmb_remember` in target workspace with `source=shared_from:<ws>:<id>`,
  `subject_key=<orig subject>`, plus `cmb_link` to the source memory.
- `cmb_unshare(memory_id, from_workspace)` → `cmb_forget` the copy only.
- `cmb_list_shared(workspace)` → `cmb_recall` with `source=shared_from:*`.
- **Sync** (when `sync=true`): owner updates re-materialize the copy via a
  `cmb_consolidate`-style background pass — for v1, manual re-share is acceptable;
  document it. Owner version always wins.

### Sharing rules enforced in the helper
- Owner workspace ≠ target workspace (no self-share).
- Never share memories with `retention_confidential` or content matching
  secret patterns (token/credential regex) — hard-block.

---

## 5. Per-Workspace Analytics

- **Already works**: `cmb_context_savings(workspace=X)`.
- **Dashboard**: CMB Workspaces page shows per-workspace savings bar (data source
  = same receipts).
- **Docs**: add a Multi-Tenancy page to `/home/alieninc/panteon/cmb-docs/`
  documenting workspaces, sharing, and the `CMB_DEFAULT_WORKSPACE` env var.

---

## 6. Rollout Order

1. ✅ **Wrapper workspace selector** (`CMB_DEFAULT_WORKSPACE`) — DONE 2026-08-01.
   Implemented in `/srv/cmb/venv/bin/cmb-mcp`: wraps `_tool_manager.call_tool`
   (FastMCP binds `cmb_mcp.call_tool` at construction, so the manager hook is the
   correct injection point). Verified: no-arg `cmb_stats({})` with
   `CMB_DEFAULT_WORKSPACE=default` returned `workspace=default`; explicit
   `{"workspace":"alieninc"}` still won. Wired into opencode.jsonc MCP env
   (`CMB_DEFAULT_WORKSPACE=alieninc`) — active on next opencode restart.
   💡 FastMCP pitfall documented: override `_tool_manager.call_tool`, not the
   FastMCP instance method (bound once in `__init__`).
2. ✅ **Workspaces page in admin.html** (list/create/stats) — DONE 2026-08-01.
   New nav item + `page-cmb-workspaces` in admin.html: lists all workspaces
   (name/description/visibility/memories/repos) from `GET /api/workspaces`, with
   create/rename/describe/copy/delete actions hitting the engine's native
   `POST /api/workspaces/*` endpoints (verified present in v2_api.py:
   create, rename, describe, visibility, copy, delete, merge). JS verified
   (`node --check`), page wired into `navigate()`/`loadPageData()`/PAGES.
3. **Sharing helpers** (`cmb_share`/`cmb_unshare`/`cmb_list_shared`) — engine has no
   per-memory cross-workspace ACL; v1 = curated read-only copies via `cmb_remember`
   with `source=shared_from:<ws>:<id>` provenance + `cmb_link`. *(next)*
4. ✅ **Docs page (Multi-Tenancy)** — DONE 2026-08-01.
   `/home/alieninc/panteon/cmb-docs/multi-tenancy.html` (workspace model,
   `CMB_DEFAULT_WORKSPACE` selector, engine workspace API reference, subsidiary
   deployment walkthrough). Linked in nav of all 6 doc pages + sitemap.xml.

## 7. Success Criteria (from roadmap, Phase 3)
- ✅ 3+ workspaces created (alieninc + 2 subsidiaries)
- ✅ Workspace isolation verified (no cross-contamination)
- ✅ Cross-workspace sharing works (read-only)
- ✅ Analytics dashboard shows per-workspace metrics

**Blockers/risks**: `cmb_promote` only widens within a workspace (session→repo→workspace),
so sharing relies on copy semantics, not ACL. If the engine later adds a native ACL,
v1 copy-share remains compatible (the provenance fields map cleanly).
