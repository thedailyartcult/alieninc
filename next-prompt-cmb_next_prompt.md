# Next-LLM Prompt: Add `cmb_next_prompt` tool to the CMB MCP server

## Handoff one-liner (paste to the next LLM)
```
cmb_recall_context(query="CMB addon fetch-ingest bridge P7 complete + external fetch server deregistered, cmb_next_prompt tool design", workspace="alieninc", token_budget=512, k=8) - then read /home/alieninc/next-prompt-cmb_next_prompt.md (spec, pushed to github.com/thedailyartcult/alieninc/blob/master/next-prompt-cmb_next_prompt.md), implement cmb_next_prompt in /root/cmb-upgrade/src/cmb/mcp_server.py (one call to service().recall_proactive for memories + last_session handoff, deterministically assemble the next session's opening prompt: Goal / Recalled context / Handoff / Open threads / Doc pointers; read-only + idempotent, _ok/_err wrappers, no new deps), rebuild via /root/cmb-upgrade/upgrade-cmb.sh + restart cmb-mcp-http.service, verify tools/list = 40 tools and one live run over HTTP :8765/mcp (initialize handshake first), update /home/alieninc/cmb-addon.md (new "Next-prompt tool" section + append-only completion log entry) and store a CMB tracking memory, end with cmb_end_session
```

**Role:** CMB platform engineer, workspace `alieninc`, repo `cmb`.

## Start (mandatory, in order)
1. `cmb_recall_proactive(workspace='alieninc', repo='cmb', k=5)`
2. `cmb_start_session(workspace='alieninc', repo='cmb', goal='Implement cmb_next_prompt MCP tool + docs update')`
3. Read `/home/alieninc/cmb-addon.md` — "Remaining work" + the append-only completion log tail — before touching anything. Do NOT re-do completed items.

## Task 1 — Implement the tool
Canonical source: `/root/cmb-upgrade/src/cmb/mcp_server.py` (rebuild via `/root/cmb-upgrade/upgrade-cmb.sh`, live service `cmb-mcp-http.service`, live DB `/srv/cmb/data/cmb.db`).
Follow the existing `@mcp.tool` pattern — see `cmb_recall_proactive` (~line 692) and `cmb_proactive_context` (~line 725). Use the `_ok(...)`/`_err(exc)` wrappers. FastMCP registers it automatically in `tools/list`.

**Spec — `cmb_next_prompt(workspace, repo=None, task="", k=10)` → JSON string:**
- Get memories + handoff with ONE call: `service().recall_proactive(workspace=..., repo=..., k=k)` (returns `memories` and `last_session` with summary/open_threads/outcome). Do not invent a new query path.
- Deterministically assemble a ready-to-paste Markdown **opening prompt for the next LLM session** with sections: **Goal** (from `task`, else last-session summary), **Recalled context** (compact bullets from `memories`), **Handoff** (summary + outcome), **Open threads** (each as a checkbox item), **Doc pointers** (always `/home/alieninc/cmb-addon.md` + `/home/alieninc/cmb-new-metrics.md`).
- Read-only + idempotent, like `cmb_recall_proactive`: `readOnlyHint=True, idempotentHint=True, openWorldHint=False`. No LLM synthesis, no receipt, no memory reinforcement.
- Return `{"workspace","repo","last_session":{...},"memories_count":N,"prompt":"<assembled markdown>"}`.

Constraints: no new dependencies, no change to other tools, keep JSON shape consistent with the server.

## Task 2 — Rebuild + verify
1. `/root/cmb-upgrade/upgrade-cmb.sh`; restart `cmb-mcp-http.service`; `cmb_health` OK (version stays 1.2.5).
2. Over HTTP `:8765/mcp` (do the `initialize` session handshake first): `tools/list` must report **40 tools** incl. `cmb_next_prompt`; run it live once with `workspace='alieninc', repo='cmb'` and confirm the assembled `prompt` contains all five sections.
3. Confirm visibility in the current opencode session (or note it needs a restart).

## Task 3 — Docs + memory
1. `/home/alieninc/cmb-addon.md`: add a short "Next-prompt tool (`cmb_next_prompt`)" section (status row `[x] done`, purpose, one-line design) and append a completion-log entry dated today (append-only). If it outgrows the addon doc, follow the `cmb-new-metrics.md` precedent and create companion doc `/home/alieninc/cmb-handoff.md` with the same header conventions.
2. `cmb_remember` a tracking memory (dedupe, mtype=episodic, kind=task_summary) — what shipped + how to verify.

## Open threads (carry in, do not close)
- Laptop (178.104.71.88) offline: once reachable, run `upgrade-cmb.sh` there so `cmb_next_prompt` exists laptop-side; verify laptop-side; laptop-network SSRF/robots re-check; cmb-new-metrics W2/W4/W5 + `ai_context.py` laptop carry-over.
- Push code to the laptop via the established sync path when it's back online.

## Constraints
- Never re-do completed work (completion log is authoritative); append-only edits; store no credentials; if a CMB call fails report it once and continue.
