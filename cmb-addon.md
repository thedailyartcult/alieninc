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
| P1 | Provision reference server: `python3.11 -m venv /srv/cmb/venv-fetch`; `pip install mcp-server-fetch==0.6.3`; verify console script + `python -m mcp_server_fetch` boots and `tools/list` returns exactly `fetch` with the documented schema | `/srv/cmb/venv-fetch`, `mcp-server-fetch==0.6.3` | [ ] not started |
| P2 | Register server in opencode config (stdio entry, venv python, NO `--ignore-robots-txt`), reload, confirm `fetch` tool visible | opencode config (opencode.json / `.opencode/`) | [ ] not started |
| P3 | Write bridge skill `.opencode/skills/fetch-ingest/`: (a) call `fetch`; (b) loop `start_index` while response contains the truncation sentinel; (c) SSRF deny-list; (d) pipe into `cmb_ingest` with `source="tool:fetch"`, `trusted=false`, `mtype="semantic"` | `.opencode/skills/fetch-ingest/SKILL.md` | [ ] not started |
| P4 | Security hardening: deny-list at bridge (deny 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, IPv6 ::1/fe80::, non-http(s) schemes) — NOT present upstream, so it lives in the bridge | bridge skill, P1 venv config | [ ] not started |
| P5 | End-to-end validation: live fetch of a known public URL → markdown → ingest → `cmb_recall_grounded` returns cited content; verify robots refusal on a robots-blocked URL; verify paging sentinel on a long page | — | [ ] not started |
| P6 | Docs + memory: update this file's status table + Completion log (append-only) and the CMB tracking memory | `cmb-addon.md`, CMB | [ ] not started |

## RESUME QUERY — give this verbatim to the next LLM doing the work
The next operator MUST start by loading CMB context, then read this file, then execute only
the phases marked `[ ] not started` in order. Do NOT re-do P0 or anything in `cmb-new-metrics.md`.

```
cmb_recall_context(query="CMB addon fetch-ingest bridge plan status and phase completions",
                   workspace="alieninc", token_budget=512, k=8)
```
Then: `cmb_recall_proactive(workspace="alieninc", repo="cmb", k=5)` for the latest session
handoff, then read `/home/alieninc/cmb-addon.md` (authoritative) and `/home/alieninc/cmb-new-metrics.md`
for completed work that must not be re-initialized.

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
