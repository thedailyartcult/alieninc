# LAPTOP CMB SETUP — Execute All Steps

You are on the laptop (178.104.71.88). Execute every step below in order.

## Step 1: Fix SSH Server

```bash
sudo sh -c 'echo "PubkeyAuthentication yes" > /etc/ssh/sshd_config.d/pubkey.conf'
sudo systemctl restart ssh
```

## Step 2: Add Server's SSH Key

```bash
grep -v "server-to-laptop" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp 2>/dev/null || true
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBpEBV+L3W6LATqeUo0ITPpBBiIdiflBsV7Ek/TLStUk server-to-laptop" >> ~/.ssh/authorized_keys.tmp
mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## Step 3: Install CMB

```bash
sudo useradd -r -s /bin/false cmb 2>/dev/null || true
sudo mkdir -p /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp
sudo chown -R cmb:cmb /srv/cmb/data /srv/cmb/web /var/log/cmb-mcp
python3 -m venv /srv/cmb/venv
/srv/cmb/venv/bin/pip install cmb-mcp
/srv/cmb/venv/bin/python3 -c "import cmb; print('CMB version:', cmb.__version__)"
```

## Step 4: Configure CMB

Create `/srv/cmb/.env`:
```
CMB_DB_PATH=/srv/cmb/data/cmb.db
CMB_PORT=8765
CMB_RETENTION_SUPERVISOR=none
```

Create `/srv/cmb/engine.py`:
```python
import os
from pathlib import Path
import cmb.dashboard_app as da
WEB = Path("/srv/cmb/web")
da._V2_ASSETS = WEB / "cmb-src"
da._INDEX = WEB / "cmb.html"
app = da.create_app()
```

## Step 5: Create systemd Services

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

Start them:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cmb-mcp-http
sudo systemctl enable --now cmb-engine
sudo systemctl status cmb-mcp-http --no-pager
```

## Step 6: Create Sync Script

Create `/home/tablet/sync-to-server.sh`:
```bash
#!/bin/bash
SERVER="root@alieninc.tech"
case "$1" in
  --push-code)
    rsync -avz --exclude='data/cmb.db' --exclude='data/*.wal' --exclude='data/*.shm' /srv/cmb/venv/ $SERVER:/srv/cmb/venv/
    rsync -avz /srv/cmb/.env /srv/cmb/engine.py $SERVER:/srv/cmb/
    ssh $SERVER "systemctl restart cmb-mcp-http"
    ;;
  --push-db)
    rsync -avz /srv/cmb/data/cmb.db $SERVER:/srv/cmb/data/cmb.db
    ssh $SERVER "systemctl restart cmb-mcp-http"
    ;;
  --status)
    echo "=== LAPTOP ==="; systemctl status cmb-mcp-http --no-pager 2>/dev/null
    echo "=== SERVER ==="; ssh $SERVER "systemctl status cmb-mcp-http --no-pager; du -sh /srv/cmb/data/*" 2>/dev/null
    ;;
  *) echo "Usage: $0 {--push-code|--push-db|--status}" ;;
esac
```
```bash
chmod +x /home/tablet/sync-to-server.sh
```

## Step 7: Verify

```bash
curl -s http://127.0.0.1:8765/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```
