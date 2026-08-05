# LAPTOP SETUP — CMB Primary Host + SSH Access

**Run this entire file through opencode on the laptop (178.104.71.88).**
It will set up SSH for the server, install/configure CMB as the primary host, and create the sync script.

---

## Step 1: Fix SSH Server

```bash
# Ensure PubkeyAuthentication is enabled
sudo sh -c 'echo "PubkeyAuthentication yes" > /etc/ssh/sshd_config.d/pubkey.conf'
sudo systemctl restart ssh

# Verify
sudo grep -r PubkeyAuthentication /etc/ssh/sshd_config /etc/ssh/sshd_config.d/ 2>/dev/null
ss -tlnp | grep :22
```

## Step 2: Add Server's SSH Key

The server's public key is:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBpEBV+L3W6LATqeUo0ITPpBBiIdiflBsV7Ek/TLStUk server-to-laptop
```

Run:
```bash
# Remove any broken/duplicate entries first
grep -v "server-to-laptop" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp || true
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBpEBV+L3W6LATqeUo0ITPpBBiIdiflBsV7Ek/TLStUk server-to-laptop" >> ~/.ssh/authorized_keys.tmp
mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cat ~/.ssh/authorized_keys
```

## Step 3: Install CMB on Laptop

```bash
# Create CMB user and directories
sudo useradd -r -s /bin/false cmb 2>/dev/null || true
sudo mkdir -p /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp
sudo chown -R cmb:cmb /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp

# Create venv and install CMB
python3 -m venv /srv/cmb/venv
/srv/cmb/venv/bin/pip install cmb-mcp

# Verify installation
/srv/cmb/venv/bin/python3 -c "import cmb; print('CMB version:', cmb.__version__)"
```

## Step 4: Configure CMB

Create `/srv/cmb/.env`:
```
CMB_DB_PATH=/srv/cmb/data/cmb.db
CMB_API_TOKEN=<use-same-token-as-server-or-generate-new>
CMB_PORT=8765
CMB_RETENTION_SUPERVISOR=none
```

Create `/srv/cmb/engine.py`:
```python
"""CMB engine launcher for laptop (primary host)."""
import os
from pathlib import Path
import cmb.dashboard_app as da

WEB = Path("/srv/cmb/web")
da._V2_ASSETS = WEB / "cmb-src"
da._INDEX = WEB / "cmb.html"
app = da.create_app()
```

## Step 5: Create systemd Services

### CMB MCP Server (port 8765)
Create `/etc/systemd/system/cmb-mcp-http.service`:
```ini
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

### CMB Dashboard (port 8700)
Create `/etc/systemd/system/cmb-engine.service`:
```ini
[Unit]
Description=CMB Memory Engine (Dashboard)
After=network.target

[Service]
Type=simple
User=cmb
Group=cmb
WorkingDirectory=/srv/cmb
EnvironmentFile=/srv/cmb/.env
ExecStart=/srv/cmb/venv/bin/uvicorn engine:app --host 127.0.0.1 --port 8700
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### Start services
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cmb-mcp-http
sudo systemctl enable --now cmb-engine
sudo systemctl status cmb-mcp-http --no-pager
sudo systemctl status cmb-engine --no-pager
```

## Step 6: Create Sync Script

Create `/home/tablet/sync-to-server.sh`:
```bash
#!/bin/bash
# Sync CMB between laptop (primary) and server (alieninc.tech)

SERVER="root@alieninc.tech"
CMB_DIR="/srv/cmb"

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
    systemctl status cmb-mcp-http --no-pager 2>/dev/null || echo "not running"
    systemctl status cmb-engine --no-pager 2>/dev/null || echo "not running"
    echo "=== DB SIZE ==="
    du -sh /srv/cmb/data/* 2>/dev/null
    echo "=== SERVER CMB ==="
    ssh $SERVER "systemctl status cmb-mcp-http --no-pager; du -sh /srv/cmb/data/*" 2>/dev/null || echo "server unreachable"
    ;;
  *)
    echo "Usage: $0 {--push-code|--pull-db|--push-db|--status}"
    ;;
esac
```

```bash
chmod +x /home/tablet/sync-to-server.sh
```

## Step 7: Verify Everything

```bash
# Test SSH from server (should work after Step 2)
# The server will run: ssh -i ~/.ssh/id_ed25519_alieninc tablet@178.104.71.88 "echo OK"

# Test CMB MCP
curl -s http://127.0.0.1:8765/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# Test CMB health
/srv/cmb/venv/bin/python3 -c "
from cmb import health
print(health.check())
"

# Test workspace
/srv/cmb/venv/bin/python3 -c "
from cmb import recall
r = recall.query('workspace:alieninc', k=1)
print(f'Memories in alieninc workspace: {len(r)}')
"
```

## Step 8: Test Cross-Machine Sync

After all steps above, from the **server** (alieninc.tech), run:
```bash
ssh -i ~/.ssh/id_ed25519_alieninc tablet@178.104.71.88 "echo 'SSH OK'; hostname; whoami"
```

If it returns `SSH OK`, the connection works.

Then test CMB sharing:
1. On laptop: store a test memory
2. On server: recall that memory
3. Both should see the same `alieninc` workspace

---

## Summary of What This Does

| Component | Laptop | Server |
|-----------|--------|--------|
| CMB MCP Server | Primary (port 8765) | Fallback (port 8765) |
| CMB Dashboard | Running (port 8700) | Disabled |
| CMB Database | Canonical copy | Synced copy |
| SSH | Server → Laptop (key auth) | Client only |
| Workspace | `alieninc` | `alieninc` |
| Sync | `--push-db`, `--push-code` | Receives updates |
