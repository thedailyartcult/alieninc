# OpenCode Guide — alieninc / panteon (for any LLM, any context window)

> **Goal:** never destroy the org structure again. Every opencode session, even a 4k-context model, must be able to work safely.

This file mirrors two pinned CMB workspace memories that every compliant agent loads automatically:
- `mem_01M19MDCS284M3CY8Q52F90WJG` — GUARDRAIL: hands-off web servers
- `mem_01M19N1K8FED6VYF64TWAARSKF` — ORG GUIDE (this document, pinned)

If CMB is unreachable, this file is the fallback.

---

## 1. Organization structure

**Workspace `alieninc`** — shared across machines:
- **Laptop (178.104.71.88)** — canonical CMB host, holds `cmb-mcp` DB
- **Hetzner server** — connects via SSH tunnel `port 8765`; fallback local at `/srv/cmb/venv/bin/cmb-mcp`
- Both read the **same** `alieninc` memories. Never assume a local-only workspace.

**Filesystem roots (all served):**
- `/home/alieninc` — `alieninc.service` WorkingDirectory, `ROOT=/home/alieninc` in `server.py`
- `/home/alieninc/panteon` — this repo (git `master`), `panteon.service` (`127.0.0.1:8000`, `panteon.main:app`)
- `/home/alieninc/centra`, `/kmt`, `/rousseau`, etc. — via `SUBDOMAIN_ROOTS` in `server.py`
- `/home/alieninc/alphazero/index.html` — served via nginx alias `/alphazero` (bypasses `server.py`)

**Deploy / serving:**
- `nginx :443/80` → `server.py` (`127.0.0.1:8080`, `systemd alieninc.service`, runs as `root`) → static files + `_html_cache` keyed by `(fs_path, mtime)` — editing a file auto-invalidates, **no restart needed** for HTML
- `Cloudflare` in front = `cf-cache-status: DYNAMIC` for HTML (never frozen)
- Panteon API: `panteon.service` on `127.0.0.1:8000`
- Sync script: `/home/tablet/sync-to-server.sh --push-code` (operator-owned, the only allowed push to prod)

**Panteon admin — the fragile heart:**
- `panteon/admin.html` — ~24,316 lines, 31 inline `<script>` blocks, one inline `<style>`, self-contained Command Deck (`DECK` at `admin.html:17621`, `navigate()` at `admin.html:5312`, `showApp()` at `admin.html:9698`)
- Critical overlays: `#platformSelectOverlay` (`admin.html:2169`, `z-index:10000`, first-run gate), `DECK` stage (`admin.html:16669` `open()` hides `.content` at `admin.html:16718`), `PLATFORM_SELECT.allowsPage` at `admin.html:5313` + `buildTools()` skipping `ps-off` at `admin.html:16465`
- **2026-08-30 incident:** router layer at `admin.html:7841` was injected as literal `\n` escapes + `el.innerHTML = "<div class="...">"` → `SyntaxError` in main block (30/31 blocks failed `node --check`), so `navigate`/`DECK` never defined and every nav click did nothing. Fix was `admin.html:7841-7848` replacement, verified `30/30` OK.

**Other invariants:**
- Design language: `panteon/AGENTS.md` is law (tokens `--bg-dark #000`, `--accent-neon #DFF140`, fonts Inter/Space Grotesk/JetBrains Mono only, no Tailwind/Bootstrap, no new colors, no third-party JS except `three.js r128` for terranean)
- Research institute: `panteon-research-institute/` (renamed from `research/`)

---

## 2. The guardrail (non-negotiable)

> **No LLM/agent, regardless of provider or context window, may mutate web servers directly.**

This means:
- Never `ssh` + `nano`/`sed`/`scp` to edit `/home/alieninc/panteon/*`, `/home/alieninc/server.py`, `nginx` configs, or any live `HTML/CSS/JS`
- Never run a shell command that writes to the production filesystem
- Every fix happens in the **local git workspace** (`/home/alieninc/panteon`), `git add` + `git commit`
- Deployment only after the **user explicitly says "deploy"** → then `sync-to-server.sh --push-code`
- If the admin is broken, fix it locally, commit, ask for approval — do not hot-patch live

Pinned as `mem_01M19MDCS284M3CY8Q52F90WJG` so it surfaces in every `cmb_recall_proactive`.

---

## 3. How opencode must work with different context windows

Opencode swaps models (different providers, 4k to 128k windows). A small model cannot dump `admin.html`. Use CMB as compressed memory:

**Session lifecycle (every task):**
```js
cmb_health()                         // version/uptime
cmb_check_update()                   // enabled:false on this fork
cmb_recall_proactive(workspace='alieninc', repo='panteon', k=5)  // loads guardrail + this guide
cmb_start_session(workspace='alieninc', repo='panteon', goal='...', agent='opencode') // keep session_id
// ... work ...
cmb_end_session(session_id, summary, outcome, open_threads=[])   // or open_threads=[...]
cmb_consolidate(workspace='alieninc', dry_run=false)             // end of session
// weekly: cmb_dedup_report(workspace='alieninc', k=50)
```

**Recall budgets (token-saving protocol):**
- Simple question: `cmb_recall_context(token_budget=256, k=5, query='...')`
- Complex/architecture: `cmb_recall_context(token_budget=512, k=8, query='...')`
- Grounded answer: `cmb_recall_grounded(min_support=0.3, query='...')`
- Never `cmb_recall` (full bodies) unless needed
- Never `read` a file without first `cmb_recall_context(query='<filename>')` — if CMB has it, use it

**Reading files:**
- Use `read(filePath, offset, limit)` — never full dumps of 24k-line files
- After reading >100 lines, `cmb_remember` the durable facts (title, structure, critical lines) for next time

**Verification before ship:**
- For any `<script>` edit in `admin.html`, run per-block `node --check` via tempfile (31 blocks) — all must pass
- `curl -s http://127.0.0.1:8080/panteon/admin.html | grep '\\\\n// Router'` must be 0
- Check console `F12` for `SyntaxError` before declaring done

---

## 4. Safe change checklist

1. Proactive recall — do you see the two pinned workspace memories? If not, `cmb_recall_context(query='guardrail')`
2. Edit **only** in `git` workspace, small `oldString`/`newString` via `edit`
3. `node --check` on every script block you touched
4. `git diff --stat` + `git status` — stage only intended files
5. Summarize fix, ask **explicit deploy approval** — do not auto-push
6. After approval, `sync-to-server.sh --push-code`; verify `curl` + `cf-cache-status`
7. Store durable lesson via `cmb_remember` (pinned if guardrail-level), `cmb_record_event` for ticks

---

## 5. Quick recovery

If admin clicks die again:
- `F12` → console — `SyntaxError` means a script block broke; run per-block `node --check` to locate
- `#platformSelectOverlay` covering viewport? → select platforms + `Launch`, `Ctrl+K`, or `Shift+click` Spinal Cracker (`sc-fusion`) to bypass DECK
- `DECK` stage hiding content? → close panels or `DECK.exitDeck()`

---

*This guide is stored as pinned CMB `mem_01M19N1K8FED6VYF64TWAARSKF` (workspace `alieninc`) and as file `panteon/OPENCODE_GUIDE.md`. Keep them in sync.*
