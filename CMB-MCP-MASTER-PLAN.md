# CMB MCP Master Plan — Dual-Machine Architecture

## Current State Audit (2026-08-05)

### What Works
- **cmb-mcp-http.service**: Running on `localhost:8765` (Streamable HTTP transport) ✅
- **CMB v1.2.5**: Installed in `/srv/cmb/venv/` ✅
- **Database**: `/srv/cmb/data/cmb.db` (1.9MB active, healthy) ✅
- **Workspace**: `alieninc` — active, receiving memories ✅
- **Alpha Zero repo**: All Phases 1-10 committed & pushed ✅

### What's Broken
- **cmb-engine.service**: CRASHING — `ModuleNotFoundError: No module named 'cmb.hosted_client'` 🔴
  - Dashboard UI at `/srv/cmb/web/` can't start
  - No nginx proxy configured for `/cmb/` path
- **180MB stale backup**: `cmb.db.bak-20260804-234024` wasting disk space
- **No laptop sync script**: `/home/tablet/sync-to-server.sh` doesn't exist on this server
- **No shared workspace config**: Laptop and server don't share CMB state

### Storage Pressure
- Server: 38GB total, 24GB used, **13GB free (67%)** — getting tight
- Laptop: Has ample storage — should be the CMB data host

---

## Architecture: Dual-Machine MCP

```
┌─────────────────────────────────────────────────────────────┐
│  LAPTOP (178.104.71.88) — "Source of Truth"                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CMB MCP Server (primary)                              │  │
│  │  - Port: 8765 (Streamable HTTP)                        │  │
│  │  - DB: /srv/cmb/data/cmb.db (SQLite)                   │  │
│  │  - Embeddings, vectors, graph data                      │  │
│  │  - Dashboard on :8700                                  │  │
│  │  - Workspace: alieninc                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  opencode (local) → stdio CMB → localhost:8765        │  │
│  │  Frontend dev workspace (alieninc repo)                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
              SSH tunnel / direct HTTP
              ssh -L 8765:127.0.0.1:8765
                          │
┌─────────────────────────────────────────────────────────────┐
│  WEB SERVER (alieninc.tech) — "Remote Client"               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  opencode (server) → stdio CMB → laptop:8765          │  │
│  │  OR: fallback local CMB if laptop unreachable          │  │
│  │  - Alpha Zero engine runs here                         │  │
│  │  - Web app on :8080                                    │  │
│  │  - Server-side agents use CMB for memory               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles
1. **Single source of truth**: Laptop holds the canonical CMB database
2. **Interchangeable access**: Both machines connect to the SAME workspace `alieninc`
3. **Storage offload**: Heavy data (embeddings, WAL, backups) live on laptop
4. **Graceful fallback**: Server has a lightweight local CMB if laptop is unreachable
5. **Token efficiency**: Every recall uses `token_budget=256`, proactive context at session start

---

## Phase A: Fix Server CMB (Immediate)

### A1. Clean Up Storage
```bash
# Remove 180MB stale backup
rm /srv/cmb/data/cmb.db.bak-20260804-234024

# Vacuum SQLite to reclaim space
/srv/cmb/venv/bin/python3 -c "
import sqlite3; conn = sqlite3.connect('/srv/cmb/data/cmb.db');
conn.execute('VACUUM'); conn.close()
"

# Verify
du -sh /srv/cmb/data/*
```

### A2. Fix cmb-engine.service (Dashboard)
The crash is `ModuleNotFoundError: cmb.hosted_client`. This is a CMB v1.2.5 packaging issue.

**Option A — Patch the import** (quick fix):
```bash
# In /srv/cmb/venv/lib/python3.11/site-packages/cmb/licensing.py
# Comment out or guard the hosted_client import
```

**Option B — Skip dashboard on server** (recommended):
The server doesn't need the dashboard — it's a headless MCP consumer.
```bash
systemctl stop cmb-engine.service
systemctl disable cmb-engine.service
```
Dashboard runs on the laptop where the full CMB package works.

### A3. Verify MCP Server Health
```bash
curl -s http://127.0.0.1:8765/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

---

## Phase B: Laptop as Primary CMB Host

### B1. Install CMB on Laptop
```bash
# On laptop (178.104.71.88)
sudo useradd -r -s /bin/false cmb
sudo mkdir -p /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp
sudo chown cmb:cmb /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp

# Create venv and install
python3 -m venv /srv/cmb/venv
/srv/cmb/venv/bin/pip install cmb-mcp

# Same .env as server (copy token)
cat > /srv/cmb/.env << 'EOF'
CMB_DB_PATH=/srv/cmb/data/cmb.db
CMB_API_TOKEN=<same-token-as-server>
CMB_PORT=8765
CMB_RETENTION_SUPERVISOR=none
CMB_DASHBOARD_URL=http://localhost:8700
EOF
```

### B2. Create Sync Script (on laptop)
```bash
#!/bin/bash
# /home/tablet/sync-to-server.sh
# Push CMB code updates from laptop to server
# Usage: ./sync-to-server.sh --push-code

SERVER="root@alieninc.tech"
CMB_SRC="/srv/cmb"

case "$1" in
  --push-code)
    echo "Pushing CMB venv + config to server..."
    rsync -avz --exclude='data/cmb.db' --exclude='data/*.wal' --exclude='data/*.shm' \
      /srv/cmb/venv/ $SERVER:/srv/cmb/venv/
    rsync -avz /srv/cmb/.env $SERVER:/srv/cmb/.env
    rsync -avz /srv/cmb/engine.py $SERVER:/srv/cmb/engine.py
    echo "Done. Restarting server services..."
    ssh $SERVER "systemctl restart cmb-mcp-http"
    ;;
  --pull-db)
    echo "Pulling latest DB from server..."
    rsync -avz $SERVER:/srv/cmb/data/cmb.db /srv/cmb/data/cmb.db
    ;;
  --push-db)
    echo "Pushing local DB to server..."
    rsync -avz /srv/cmb/data/cmb.db $SERVER:/srv/cmb/data/cmb.db
    ssh $SERVER "systemctl restart cmb-mcp-http"
    ;;
  --status)
    echo "=== LAPTOP CMB ==="
    systemctl status cmb-mcp-http --no-pager
    echo "=== DB SIZE ==="
    du -sh /srv/cmb/data/*
    echo "=== SERVER CMB ==="
    ssh $SERVER "systemctl status cmb-mcp-http --no-pager; du -sh /srv/cmb/data/*"
    ;;
  *)
    echo "Usage: $0 {--push-code|--pull-db|--push-db|--status}"
    ;;
esac
```

### B3. Laptop systemd Services
```ini
# /etc/systemd/system/cmb-mcp-http.service (laptop)
[Unit]
Description=CMB MCP Server (Primary)
After=network.target

[Service]
Type=simple
User=cmb
Group=cmb
ExecStart=/srv/cmb/venv/bin/cmb-mcp-http
EnvironmentFile=/srv/cmb/.env
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## Phase C: Server Connects to Laptop CMB

### C1. SSH Tunnel (Persistent)
```ini
# /etc/systemd/system/cmb-tunnel.service (on server)
[Unit]
Description=SSH tunnel to laptop CMB
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 root@178.104.71.88
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### C2. Server CMB Config — Point to Tunnel
```bash
# /srv/cmb/.env on server (modified)
CMB_DB_PATH=/srv/cmb/data/cmb.db   # local fallback cache
CMB_API_TOKEN=<same-token>
CMB_PORT=8765                       # tunnel forwards to laptop
CMB_REMOTE_MCP_URL=http://127.0.0.1:8765/mcp  # via tunnel
CMB_RETENTION_SUPERVISOR=none
```

### C3. opencode Config — Server Side
The server's opencode connects to CMB via stdio (local venv), which proxies to laptop through the tunnel:
```json
// opencode.json (server)
{
  "mcp": {
    "cmb": {
      "type": "stdio",
      "command": "/srv/cmb/venv/bin/cmb-mcp",
      "env": {
        "CMB_DB_PATH": "/srv/cmb/data/cmb.db",
        "CMB_REMOTE_MCP_URL": "http://127.0.0.1:8765/mcp"
      }
    }
  }
}
```

---

## Phase D: Token Optimization — The "Standard Prompt"

### D1. opencode Agent Instructions (Both Machines)
This is the **standard prompt** to use in `AGENTS.md` on BOTH machines:

```markdown
# CMB MCP Protocol (MANDATORY — both laptop and server)

## Workspace
- Workspace name: `alieninc` (shared between laptop and server)
- Both machines access the SAME CMB database via the primary MCP server

## Before Every Task
1. `cmb_recall_proactive(workspace='alieninc', repo='<current-repo>', k=5)`
2. Use `cmb_start_session(workspace='alieninc', repo='<repo>', goal='<task>')`
3. Use the bootstrap handoff to resume prior work

## Recall Rules (Token Budget)
- **Simple queries**: `cmb_recall_context(token_budget=256, k=5)`
- **Complex architecture**: `cmb_recall_context(token_budget=512, k=8)`
- **Grounded answers**: `cmb_recall_grounded(min_support=0.3)`
- NEVER use `cmb_recall` (full bodies) unless explicitly needed

## Memory Storage Rules
- Store ONLY durable facts: decisions, conventions, bug fixes, architecture
- Title format: `"<topic>: <brief description>"`
- Use `cmb_remember(dedupe=True)` — never duplicate
- Use `cmb_record_event` for logs/ticks, not `cmb_remember`
- NEVER store: full file contents, credentials, raw logs, scratch state

## Session Lifecycle
- Start: `cmb_start_session` with workspace, repo, goal
- End: `cmb_end_session` with summary + open_threads
- Auto-resume: bootstrap injects prior session context

## File Reading Protocol
1. Check CMB first: `cmb_recall_context(token_budget=256, query='<filename>')`
2. If CMB has it: use that context, skip file read
3. If not: read with `offset` + `limit`, never full dumps
4. After reading >100 lines: `cmb_remember` the structure summary

## Consolidation
- End of session: `cmb_consolidate(workspace='alieninc', dry_run=False)`
- Weekly: `cmb_dedup_report(workspace='alieninc', k=50)`
```

### D2. Expected Token Savings
| Before | After | Savings |
|--------|-------|---------|
| Full file reads (5-50KB each) | CMB recall (256-512 tokens) | **90-95%** |
| Re-asking user for known info | Proactive recall | **100%** |
| Re-reading same files every session | Cached CMB context | **80%** |
| No session continuity | Bootstrap handoff | **Varies** |

---

## Phase E: Verification & Testing

### E1. Health Checks (Both Machines)
```bash
# Server
curl -s http://127.0.0.1:8765/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"healthcheck","version":"1.0"}}}'

# Laptop (same command)

# Verify shared workspace
/srv/cmb/venv/bin/python3 -c "
from cmb import recall
result = recall.query('workspace:alieninc', k=5)
print(f'Memories found: {len(result)}')
"
```

### E2. Cross-Machine Test
1. Store a memory on laptop: `cmb_remember(workspace='alieninc', content='CROSS-MACHINE-TEST-42')`
2. Recall on server: `cmb_recall(query='CROSS-MACHINE-TEST', workspace='alieninc')`
3. Verify the memory appears on both machines

### E3. Alpha Zero Integration Test
```bash
# Verify Alpha Zero engine can reach CMB
cd /home/alieninc/alphazero/alpha-zero-engine
python -c "
from cmb import mcp_server
print('CMB MCP accessible')
"
```

---

## Execution Order

| Step | Action | Machine | Time |
|------|--------|---------|------|
| A1 | Clean stale backup, vacuum DB | Server | 2min |
| A2 | Disable broken cmb-engine on server | Server | 1min |
| A3 | Verify MCP health | Server | 1min |
| B1 | Install CMB on laptop | Laptop | 5min |
| B2 | Create sync script | Laptop | 2min |
| B3 | Start laptop CMB service | Laptop | 1min |
| C1 | Create SSH tunnel service | Server | 2min |
| C2 | Configure server to use tunnel | Server | 2min |
| D1 | Update AGENTS.md on both machines | Both | 5min |
| E1-E3 | Run verification tests | Both | 5min |

**Total estimated time: ~25 minutes**

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Laptop unreachable | Server keeps local CMB as fallback (stdio mode) |
| SSH tunnel drops | systemd auto-restarts tunnel; CMB falls back to local DB |
| DB corruption | Daily backups via sync script `--push-db` |
| Token waste | Strict `token_budget=256` default, dedupe on write |
| Version mismatch | Sync script ensures same CMB version on both machines |
