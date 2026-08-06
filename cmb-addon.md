# CMB Add-On — Web Fetch → Memory Ingest Bridge

**Workspace:** `alieninc` (shared, laptop + server)
**Repo:** `cmb`
**Authoritative tracking doc:** this file — `/home/alieninc/cmb-addon.md`
**Companion completed-plan doc (do NOT re-do):** `/home/alieninc/cmb-new-metrics.md` (W1–W8 ALL COMPLETE, 2026-08-06)
**Canonical CMB source:** `/root/cmb-upgrade/src/cmb` (server) / `/home/tablet/cmb-upgrade/src/cmb` (laptop)
**Build/deploy:** `/root/cmb-upgrade/upgrade-cmb.sh` (rebuild + restart `cmb-mcp-http.service`)
**Live DB:** `/srv/cmb/data/cmb.db`
**Started:** 2026-08-06

## Status Legend
- [ ] not started
- [x] done
- [ ] 🔶 in progress / partial

## Goal
Give CMB a **web → memory** primitive: fetch a live URL, convert it to markdown (using the
exact, upstream-verified Anthropic reference implementation), and pipe the result into
`cmb_ingest` so the page becomes durable, recallable memory. No media, no model-routing,
no new LLM backend — this is purely the **fetch** capability plus a thin ingest bridge.

## What we are adopting (VERIFIED from upstream source — do not invent variants)
Everything below is quoted from the live repo `github.com/modelcontextprotocol/servers`
branch `main`, directory `src/fetch`. Fetch dates: 2026-08-06. Re-verify with the exact URLs
in the "Verification sources" section before changing anything.

### 1. Package identity — `src/fetch/pyproject.toml`
- name = `mcp-server-fetch`, version = **0.6.3**
- author = **"Anthropic, PBC."** (maintainer Jack Adamson, jadamson@anthropic.com)
- license = **MIT**, requires-python = **>=3.10**
- dependencies: `httpx>=0.27`, `markdownify>=0.13.1`, `mcp>=1.1.3`, `protego>=0.3.1`,
  `pydantic>=2.0.0`, `readabilipy>=0.2.0`, `requests>=2.32.3`
- console script: `mcp-server-fetch = "mcp_server_fetch:main"`

### 2. Entry points (verified)
- Console: `mcp-server-fetch` (via pyproject `[project.scripts]`)
- Module: `python -m mcp_server_fetch` (`src/fetch/src/mcp_server_fetch/__main__.py` → `main()`)
- CLI args (`__init__.py`, `main()`): `--user-agent STR`, `--ignore-robots-txt`,
  `--proxy-url STR` → passed to `serve(user_agent, ignore_robots_txt, proxy_url)`
- Transport: **stdio only** — `server.py` line 287: `async with stdio_server() ...`
- Server instance name: `Server("mcp-fetch")` (line 193)

### 3. THE function — tool `fetch` (verified, `server.py` lines 197–255)
- `list_tools()` returns exactly ONE tool: `name="fetch"` (line 201), description:
  "Fetches a URL from the internet and optionally extracts its contents as markdown.
  Although originally you did not have internet access ... this tool now grants you internet access."
- `inputSchema = Fetch.model_json_schema()` (line 205). Schema fields (`class Fetch`, lines 151–178):
  - `url` — string, **required**, type `AnyUrl`
  - `max_length` — int, default **5000**, constraint `0 < x < 1000000`
  - `start_index` — int, default **0**, constraint `>= 0` (paging)
  - `raw` — bool, default **false** (get raw HTML without markdown conversion)
- Behavior on call (lines 223–255):
  1. robots.txt check `check_may_autonomously_fetch_url(...)` (line 234) **unless**
     `--ignore-robots-txt` (Protego parser; 401/403 → refuse, other 4xx → allow)
  2. `fetch_url(url, user_agent_autonomous, force_raw, proxy)` (line 237): httpx GET,
     `follow_redirects=True`, `timeout=30`; status >= 400 → `McpError`
  3. HTML detection (lines 138–140): `<html` in first 100 chars **OR** `text/html` in
     content-type **OR** empty content-type
  4. Markdown extraction (line 142): `readabilipy.simple_json.simple_json_from_html_string(use_readability=True)`
     → `markdownify.markdownify(heading_style=ATX)` — helper `extract_content_from_html` (line 27)
  5. Truncation/paging (lines 240–254): slices `content[start_index : start_index + max_length]`;
     if truncated appends `<error>Content truncated. Call the fetch tool with a start_index of {next_start} to get more content.</error>`;
     past end returns `<error>No more content available.</error>`
  6. Response format (line 255): `TextContent(text=f"{prefix}Contents of {url}:\n{content}")`
- Also exposes a `fetch` **prompt** (lines 209–221, 257–284): required `url` arg, manual
  User-Agent, robots check NOT applied on the prompt path.
- User-Agent constants (lines 23–24): autonomous/manual
  `ModelContextProtocol/1.0 (Autonomous; +https://github.com/modelcontextprotocol/servers)`

### 4. Known security caveat (from the repo's own `README.md`, CAUTION block)
> "This server can access local/internal IP addresses and may represent a security risk."
There is **no SSRF filter in the upstream source** — robots.txt is the only pre-check. Our
bridge layer MUST add its own deny-list (see P4).

### 5. Verification sources (exact upstream URLs, re-check before ANY change)
- Tree: https://github.com/modelcontextprotocol/servers/tree/main/src/fetch
- Source: https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/src/mcp_server_fetch/server.py
- Entry:  https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/src/mcp_server_fetch/__init__.py
- Main:   https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/src/mcp_server_fetch/__main__.py
- Build:  https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/pyproject.toml
- Docs:   https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/README.md
- Tests:  https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/fetch/tests/test_server.py

## Architecture of the add-on (decided)
```
open-code agent
   │ 1. calls tool "fetch" (upstream reference server, stdio, our venv)
   ▼
mcp-server-fetch (v0.6.3, Anthropic)  →  markdown text
   │ 2. bridge protocol (paging until sentinel, SSRF deny-list)
   ▼
cmb_ingest(content=<page markdown>, workspace="alieninc",
           mtype="semantic", source="tool:fetch", trusted=false)
   ▼
CMB memory (durable, recallable; receipts carry token_usage)
```
Two code surfaces:
- **Reference server** — adopted as-is (no forks). Installed in its own venv.
- **Bridge** — opencode-side protocol (paging loop + SSRF deny-list + ingest mapping),
  codified as a skill file under `.opencode/skills/fetch-ingest/` so every agent follows
  the same steps. NO changes to CMB core source.

## Phases / status
| # | Task | Files/commands | Status |
|---|------|----------------|--------|
| P0 | Lock baseline: cmb-new-metrics W1–W8 already complete (do not re-do); CMB v1.2.5, PID 3107661, DB owner `cmb:cmb`, service active; this tracking memory exists in CMB | `cmb-addon.md`, CMB memory | [x] done |
| P1 | Provision reference server: `python3.11 -m venv /srv/cmb/venv-fetch`; `pip install mcp-server-fetch==0.6.3`; verify console script + `python -m mcp_server_fetch` boots and `tools/list` returns exactly `fetch` with the documented schema | `/srv/cmb/venv-fetch`, `mcp-server-fetch==0.6.3` | [x] done |
| P2 | Register server in opencode config (stdio entry, venv python, NO `--ignore-robots-txt`), reload, confirm `fetch` tool visible | opencode config (opencode.json / `.opencode/`) | [x] done |
| P3 | Write bridge skill `.opencode/skills/fetch-ingest/`: (a) call `fetch`; (b) loop `start_index` while response contains the truncation sentinel; (c) SSRF deny-list; (d) pipe into `cmb_ingest` with `source="tool:fetch"`, `trusted=false`, `mtype="semantic"` | `.opencode/skills/fetch-ingest/SKILL.md` | [x] done |
| P4 | Security hardening: deny-list at bridge (deny 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, IPv6 ::1/fe80::, non-http(s) schemes) — NOT present upstream, so it lives in the bridge | bridge skill, P1 venv config | [x] done |
| P5 | End-to-end validation: live fetch of a known public URL → markdown → ingest → `cmb_recall_grounded` returns cited content; verify robots refusal on a robots-blocked URL; verify paging sentinel on a long page | — | [x] done |
| P6 | Docs + memory: update this file's status table + Completion log (append-only) and the CMB tracking memory | `cmb-addon.md`, CMB | [x] done |
| P7 | Native integration: build the fetch capability INTO CMB (`cmb_fetch` + `cmb_fetch_ingest` MCP tools + `source`/`trusted` on `cmb_ingest`), replacing the external bridge so both laptop and server get it from the shared source | `cmb/fetchutil.py`, `cmb/mcp_server.py`, rebuild | [x] done |

## RESUME QUERY — give this verbatim to the next LLM doing the work
CMB native fetch-ingest is **implemented but NOT finished**: P0–P7 complete (2026-08-06),
and there is still refinement + integration work the user wants done (see **Remaining
work** below). Do NOT re-run or re-plan completed phases, and do NOT re-initialize
anything in `cmb-new-metrics.md` (W1–W8 complete). What is DONE: fetch is native in CMB —
`cmb_fetch` (SSRF-guarded, robots-always-on, paging), `cmb_fetch_ingest` (fetch + store,
`source=tool:fetch, trusted=false, kind=web`, title defaults to the URL), a `fetch` MCP
prompt, and `source`/`trusted`/`title` params on `cmb_ingest` (the P5 provenance DEVIATION
is resolved). The external `/srv/cmb/venv-fetch` server + its `/home/alieninc/opencode.jsonc`
entry are REDUNDANT (kept as reference). The user has restarted opencode and expects the
native tools in-session; do NOT claim completion — verify, refine, integrate, and report
concrete next steps.

```
cmb_recall_context(query="CMB addon fetch-ingest bridge P7 complete, remaining refinement and integration work",
                   workspace="alieninc", token_budget=512, k=8)
```
Then: `cmb_recall_proactive(workspace="alieninc", repo="cmb", k=5)` for the latest session
handoff, then read `/home/alieninc/cmb-addon.md` (authoritative — start at **Remaining
work** below) and `/home/alieninc/cmb-new-metrics.md` for completed work that must not be
re-initialized. End the session with `cmb_end_session` + a summary that includes the
concrete next steps you found, not just a status.

## Remaining work (refinement & integration — NOT finished)

Refinement (code, canonical source `/root/cmb-upgrade/src/cmb`):
1. **Laptop deployment** (laptop offline now): run `upgrade-cmb.sh` on the laptop so native
   `cmb_fetch`/`cmb_fetch_ingest`/`fetch` prompt exist there too; verify `tools/list` +
   one live fetch on the laptop side. Then decide: deregister the redundant external
   `fetch` server from `/home/alieninc/opencode.jsonc` and retire `/srv/cmb/venv-fetch`.
2. **In-session verification** after the opencode restart: confirm the three surfaces appear
   under the `cmb` server in the actual MCP client, and run one fetch→ingest→grounded-recall
   round trip end to end from the user's own session.
3. **`cmb_fetch` response shape — RESOLVED (2026-08-06)**: stays raw text (not a JSON
   envelope), deliberately — upstream parity, best for direct agent consumption; the skill
   documents this and its paging loop operates on raw text.
4. **MCP session protocol — DONE (2026-08-06)**: `_SESSION_PROTOCOL` in `mcp_server.py`
   now names `cmb_fetch_ingest`/`cmb_fetch` as a first-class primitive (provenance +
   never-bypass the SSRF/robots guards). Ships in the next rebuild (this is that rebuild).
5. **REST provenance parity — re-scoped as OPTIONAL**: the REST ingest path
   (`routes/memory.py` → `engines/ingest.ingest_document` → `upsert_memory`) is the legacy
   namespace/document pipeline and has no modern `source`/`trusted`/`kind` model; adding it
   is a provenance retrofit, not a quick tweak. Only do it if a real API client needs it.
6. **Robots/SSRF parity check on the laptop network**: egress/proxies differ from the
   server — re-verify SSRF deny cases and robots refusal there.

Integration (workflow):
7. **Consolidation — RESOLVED (dry-run 2026-08-06)**: `cmb_consolidate(repo=cmb, dry_run)`
   reports 0 clusters — fetched pages are distinct single semantic memories (web-provenance),
   not recurring episodic clusters, so they are not consolidation candidates. No action.
8. **Reusable "web research → memory" workflow**: wire fetch-ingest into a repeatable
   session pattern (fetch → ingest → recall_grounded citations) and store the procedure.
9. **cmb-new-metrics carry-over**: laptop-side verification of W2/W4/W5 + `ai_context.py`
   remains pending from that doc.

Context-window note (opencode with different providers): if the provider's window is small,
do NOT paste upstream source into the prompt — re-fetch only the single file you are touching
from the "Verification sources" list above; the md already pins exact file:line references.

## Completion log (append-only — never re-do completed items)
- **2026-08-06** P0 locked: cmb-new-metrics W1–W8 verified complete (recall + live checks:
  service active, DB owner `cmb:cmb`, ExecStartPre chown present, consolidation cron present,
  `ai_context.py` installed in site-packages; laptop offline → laptop-side verification still
  an open thread from the metrics doc). Upstream `mcp-server-fetch` v0.6.3 source verified
  directly from `modelcontextprotocol/servers@main` (tool `fetch`, schema, robots, truncation,
  stdio transport — see "What we are adopting"). Plan + this memory stored in CMB.
- **2026-08-06** P1 done: `/srv/cmb/venv-fetch` provisioned (python3.11, owned `cmb:cmb`).
  `mcp-server-fetch==0.6.3` is NOT on PyPI (latest published 0.6.2) → installed the EXACT
  verified source from `modelcontextprotocol/servers@main#subdirectory=src/fetch`
  (same version string 0.6.3, wheel built from upstream). One venv-level pin added:
  `mcp<2` → 1.29.0 (upstream declares `mcp>=1.1.3` but mcp 2.0.0 removed the `McpError`
  API the server imports; no source change). Verified BOTH entry points boot and
  `tools/list` returns exactly one tool `fetch` with the documented schema
  (url required, max_length 5000 0<x<1e6, start_index>=0, raw bool).
- **2026-08-06** P2 done: fetch stdio server registered at project level
  `/home/alieninc/opencode.jsonc` (deep-merges with global config; `type: local`,
  command `/srv/cmb/venv-fetch/bin/mcp-server-fetch`, NO `--ignore-robots-txt`,
  enabled, timeout 60000). JSON-valid; shape matches the working `cmb-local` entry.
  In-session tool visibility is pending an opencode restart (config not hot-reloaded).
- **2026-08-06** P3 done: bridge skill written at `.opencode/skills/fetch-ingest/SKILL.md`
  (frontmatter name+description per opencode skill loader). Steps: (1) SSRF URL guard
  before ANY fetch, (2) `fetch` call with paging loop on the exact upstream truncation
  sentinel, (3) `cmb_ingest` mapping `workspace=alieninc, repo=cmb, mtype=semantic,
  scope=repo, source=tool:fetch, trusted=false`, (4) confirm + report incl. robots-refusal
  handling. NO bypass of robots, NO spidering, `max_length` capped at 10000 absent consent.
- **2026-08-06** P4 done: SSRF deny-list codified BOTH as skill prose AND as an executable
  stdlib guard `check_url.py` (exit 0 = SAFE, exit 1 = blocked with reason) so every agent
  enforces identical rules. Denies non-http(s) schemes, host-literal deny (localhost,
  metadata hostnames, `*.local/*.internal/*.lan/*.home`), and resolved-IP ranges
  127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254.0.0/16, 0.0.0.0/8, ::1, ::, fe80::/10,
  fc00::/7 — checked per-address to block DNS rebinding. Live-tested: 8 deny cases all
  blocked, `https://example.com` passes.
- **2026-08-06** P5 done (e2e, driven via MCP client against the exact registered command):
  (1) SSRF guard SAFE on example.com/Wikipedia; 8 deny cases blocked. (2) Live fetch OK —
  response prefix `Contents of {url}:` confirmed, markdown extracted. (3) Paging verified:
  truncation sentinel `<error>Content truncated. Call the fetch tool with a start_index of
  {next} to get more content.</error>` parsed, loop reassembled a 19,451-char Wikipedia
  article in 4 pages; past-end `<error>No more content available.</error>` confirmed.
  (4) Robots refusal verified: `https://www.google.com/search?q=cmb` refused by Google's
  robots.txt (autonomous UA), while allowed pages fetch fine. (5) Ingest→grounded:
  article ingested, `cmb_recall_grounded` returned grounded:true with citation
  mem_01KZASY3RAEWWC044VKPEEFRVH carrying `source=tool:fetch, trusted=false`.
  DEVIATION (recorded in skill): `cmb_ingest` MCP schema has NO source/trusted params and
  stores `agent/trusted:true`; with no extractor it is passthrough anyway → bridge uses
  `cmb_remember(source="tool:fetch", trusted=false)` so the memory-poisoning guard holds.
  Server stdout verified clean (pure JSON-RPC, one tool). Note: in-session `fetch` tool
  visibility in opencode needs a restart (config not hot-reloaded).
- **2026-08-06** P6 done: this file's status table all `[x] done`; completion log entries
  for P1–P6 appended (append-only); CMB tracking memory updated. The bridge is complete:
  upstream reference server in `/srv/cmb/venv-fetch`, project config registration
  `/home/alieninc/opencode.jsonc`, skill `.opencode/skills/fetch-ingest/` (paging loop,
  SSRF guard `check_url.py`, provenance-guarded ingest). Open thread: opencode restart to
  surface the `fetch` tool in-session.
- **2026-08-06** P7 done — NATIVE integration (fix for "why is this outside tooling?"):
  the fetch capability is now a built-in CMB MCP feature, no external server needed.
  (1) New stdlib-lazy module `cmb/fetchutil.py` (canonical source
  `/root/cmb-upgrade/src/cmb/fetchutil.py`): SSRF deny-list guard (same list as P4 —
  127/8, 10/8, 172.16/12, 192.168/16, 169.254.0.0/16, 0.0.0.0/8, ::1, ::, fe80::/10,
  fc00::/7, localhost + metadata hostnames + `*.local/*.internal/*.lan/*.home`,
  non-http(s) schemes, per-address DNS-rebinding check), robots.txt ALWAYS enforced
  (Protego primary, minimal stdlib parser fallback; 401/403 → refuse, other 4xx → allow),
  httpx fetch (follow_redirects, UA, timeout 30, >=400 → error), HTML→markdown via
  readabilipy+markdownify with raw-content graceful degradation. (2) Two new MCP tools in
  `cmb/mcp_server.py`: `cmb_fetch` (url/max_length/start_index/raw; paging sentinel EXACTLY
  matches upstream `<error>Content truncated...start_index of {next}</error>`; read-only,
  viewer role) and `cmb_fetch_ingest` (url/workspace/repo/session_id/max_length/raw/mtype/
  scope; fetches whole page then stores via `service().ingest` with
  `source="tool:fetch", trusted=false, kind="web"`; admin role). (3) `cmb_ingest` MCP tool
  now exposes `source` and `trusted` params — the P5 provenance DEVIATION is RESOLVED
  (service.ingest always supported them; the MCP binding just omitted them). (4) Optional
  `fetch` extra added to `pyproject.toml` (httpx, protego, markdownify, readabilipy);
  installed into `/srv/cmb/venv` (added beautifulsoup4, html5lib, lxml, markdownify 1.2.3,
  protego 0.6.2, readabilipy 0.3.0, six, soupsieve, webencodings). (5) Rebuilt via
  `upgrade-cmb.sh` (still version 1.2.5, wheel rebuilt), `cmb-mcp-http.service` restarted.
  VERIFIED live over HTTP (port 8765, the tunnel the laptop connects through): tools/list
  = 39 tools incl. cmb_fetch + cmb_fetch_ingest with correct schemas; example.com fetches
  to markdown; Google /search robots refusal returned as error (not bypassable);
  Wikipedia paging sentinel + start_index continuation correct; cmb_fetch_ingest created
  mem_01KZAWDKNSCYEECWV4PEKJNCN9 with provenance `{source: tool:fetch, trusted: false,
  kind: web}` and dedupe noop on retry. Because the HTTP wrapper reuses
  `mcp_server.mcp`, the tools are live on both stdio and HTTP everywhere CMB is installed —
  the laptop gets them on next `upgrade-cmb.sh` run. NOTE: `/srv/cmb/venv-fetch` + the
  external `fetch` registration in `/home/alieninc/opencode.jsonc` are now REDUNDANT
  (kept as reference; safe to deregister once native tools are confirmed in-session).
  Open threads now: (a) laptop offline → laptop-side verification of native tools +
  cmb-new-metrics W2/W4/W5 still pending; (b) optional deregistration of the external
  fetch server.
- **2026-08-06** P7 follow-up refinements (done, before the user's opencode restart):
  (1) `title` now supported END-TO-END on the ingest path — added optional `title` to
  `service().ingest` and `core/engine.ingest` (passthrough `ExtractedFact(content, title)`;
  extractor path unaffected), and `cmb_fetch_ingest` re-exposes `title` defaulting to the
  fetched URL. Verified live: `cmb_fetch_ingest(url=https://example.org/, title=...)` stored
  mem_01KZAX70K9MX22R0VT164P828E with the given title AND provenance
  `{source: tool:fetch, trusted: false, kind: web}` (op=invalidate via dedupe supersession).
  (2) `fetch` MCP **prompt** added (upstream-parity; FastMCP `@mcp.prompt`, instructs the
  paging loop + provenance-guarded ingest) — `prompts/list` now returns `fetch`.
  (3) `cmb_fetch` now increments the `cmb_health` tool-call counter (it returns raw text so
  it bypasses `_ok`). Rebuilt via `upgrade-cmb.sh`, service restarted, live-verified over
  HTTP :8765. NOTE: the work is intentionally NOT declared finished — see **Remaining
  work** section (laptop deployment + in-session verification, `cmb_fetch` response-shape
  decision, MCP protocol/AGENTS.md integration, REST `source`/`trusted`/`title` parity,
  consolidation/workflow integration, cmb-new-metrics laptop carry-over).
- **2026-08-06** P7 continuation (unblocked server-side items only): (1) **protocol
  integration** — `_SESSION_PROTOCOL` in `mcp_server.py` now names `cmb_fetch_ingest` /
  `cmb_fetch` as a first-class primitive (provenance + never-bypass SSRF/robots); rebuilt +
  restarted, verified live: instructions carry the paragraph, 39 tools, `cmb_fetch_ingest`
  schema has `title`, `prompts/list` returns `fetch`, `cmb_fetch(example.org)` returns
  markdown. (2) **Response-shape decision RESOLVED**: `cmb_fetch` stays raw text (upstream
  parity, agent-friendly); documented in the skill. (3) **Consolidation RESOLVED**:
  `cmb_consolidate(repo=cmb, dry_run)` = 0 clusters; fetched pages are distinct single
  semantic memories, not consolidation candidates. (4) **REST provenance parity re-scoped
  OPTIONAL**: REST ingest is the legacy `engines/ingest.ingest_document` pipeline without the
  modern source/trusted/kind model — would be a provenance retrofit, only if an API client
  needs it. STILL OPEN (next session): laptop deployment + in-session verification after the
  opencode restart, laptop-network SSRF/robots re-check, reusable web-research workflow
  procedure, cmb-new-metrics laptop carry-over (W2/W4/W5 + ai_context.py), optional
  deregistration of the external fetch server.
