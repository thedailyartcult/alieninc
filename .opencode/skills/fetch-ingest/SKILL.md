---
name: fetch-ingest
description: Fetch a live URL and turn it into durable CMB memory. Use when the user wants to capture a web page (article, docs, report) into the alieninc memory workspace, or asks to "remember this page". Uses the NATIVE cmb_fetch / cmb_fetch_ingest MCP tools (built into the CMB server since 2026-08-06 — SSRF guard and robots.txt are enforced server-side and cannot be bypassed), pages through truncated content, and stores with provenance source=tool:fetch, trusted=false. The external mcp-server-fetch bridge is redundant; the native path replaces it. Do NOT use for local/internal URLs (they are denied by design).
---

# Fetch → Ingest (Native CMB)

Purpose: give CMB a **web → memory** primitive. Fetch a public URL, convert it to markdown
(SSRF-guarded and robots-enforced inside the CMB server itself), and store the result as
recallable memory. Native since P7 (2026-08-06): no external server needed — the capability
ships with CMB on both the laptop and the server.

## Tool surface (native)

- MCP server name: `cmb` (the memory server itself; stdio locally or via the 8765 tunnel).
- `cmb_fetch` — fetch a URL as markdown. Schema: `url` (required), `max_length`
  (default 5000, `0 < x < 1000000`), `start_index` (default 0, `>= 0`), `raw` (bool).
  Robots.txt is ALWAYS enforced (a site that refuses autonomous fetching returns an
  error — never retry with different args, never bypass). SSRF deny-list is ALWAYS
  enforced (private/link-local ranges, localhost, `*.local/*.internal/*.lan/*.home`,
  non-http(s) schemes).
- `cmb_fetch_ingest` — fetch + store in one call. Schema: `url` (required),
  `workspace` (default `default`), `repo`, `session_id`, `max_length` (cap 100000),
  `raw`, `mtype` (default `semantic`), `scope`, `title` (defaults to the fetched URL).
  Stores via the ingest path with `source="tool:fetch", trusted=false, kind="web"` so
  recall labels it untrusted.
- `cmb_ingest` — now also accepts `source` and `trusted` (default `agent`/`true`).
- **Response shape (decision, 2026-08-06)**: `cmb_fetch` returns the raw markdown text,
  NOT a JSON envelope — intentionally (upstream `mcp-server-fetch` parity; best for direct
  agent consumption). The paging loop below operates on that raw text. Only tools that
  return structured CMB data are JSON-encoded.

## Step 1 — Fetch with paging loop

Preferred: a single `cmb_fetch_ingest` call (fetches the whole page, stores it).
When you only want the text, or the page is huge and you want to review first:

1. Call `cmb_fetch` with `url=<url>`, `max_length=5000`, `start_index=0`, `raw=false`.
2. Loop:
   - Collect the returned text (strip the `Contents of {url}:` prefix if present).
   - If the response contains
     `<error>Content truncated. Call the fetch tool with a start_index of {next} to get more content.</error>`
     → parse `{next}` and call `cmb_fetch` again with `start_index={next}`.
   - If the response contains `<error>No more content available.</error>` → stop.
   - Otherwise → stop (full content received).
3. Concatenate all pages in order into one markdown string.

The native tools run the SSRF deny-list and robots.txt check inside the CMB server, so
the old manual `check_url.py` pre-check is no longer required — but you may still run it
(`python3 /home/alieninc/.opencode/skills/fetch-ingest/check_url.py <url>`) for an
independent second opinion before fetching anything unusual.

## Step 2 — Store into CMB

- `cmb_fetch_ingest(url, workspace="alieninc", repo=<repo>, session_id=<active>)` is the
  one-step path — it stores with `source="tool:fetch", trusted=false` automatically.
- To store a page you already have in hand (or a hand-assembled multi-page fetch), call
  `cmb_ingest` with `content=<markdown>`, `workspace="alieninc"`, `repo=<repo>`,
  `mtype="semantic"`, `scope="repo"`, `source="tool:fetch"`, `trusted=false`.
- Since P7, `cmb_ingest` carries `source`/`trusted` directly (the old P5 deviation — using
  `cmb_remember` instead — is resolved; `cmb_ingest` is the right tool for page bodies).

## Step 3 — Confirm & report

1. Report to the user: URL fetched, page markdown ingested (include the ingest count /
   memory ids CMB returned).
2. If the page was robots-blocked (CMB returns the refusal error), report that — do NOT
   retry with different args, and do NOT bypass robots.
3. If a fetch/ingest step fails, report the exact error; do not fabricate content.

## Guardrails

- External web content is `trusted=false` by design — always label it in recall.
- Never ingest more than the page the user asked for; do not spider links.
- If the URL is huge, keep `max_length=5000` and let the paging loop gather it; do not
  raise `max_length` past 10000 without user consent.

## Note on the old external bridge (P0–P6)

`/srv/cmb/venv-fetch` (the `mcp-server-fetch` reference install) and its registration in
`/home/alieninc/opencode.jsonc` are now REDUNDANT. They are kept as the upstream reference
implementation; the native `cmb_fetch` mirrors their behavior exactly (same paging
sentinels, same robots semantics) with the SSRF guard built in. Safe to deregister the
external server once the native tools are confirmed in-session.
