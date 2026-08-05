# LAPTOP REVERSE TUNNEL SETUP — Expose CMB to the Web Server

**Execute this file on the laptop via opencode.** It creates a persistent reverse SSH tunnel so the web server can reach this laptop's CMB even though the laptop is behind NAT.

## Why
- The laptop (this machine) is behind home NAT — the server cannot initiate SSH to it.
- The laptop CAN initiate SSH to the server (already proven by `sync-to-server.sh`).
- Solution: the laptop keeps a **reverse tunnel** open to the server, forwarding its CMB port (8765) to the server's `127.0.0.1:8766`.
- The server's opencode then talks to `127.0.0.1:8766` — which IS this laptop's CMB. Shared brain.

## Step 1: Verify CMB is running locally

```bash
curl -s http://127.0.0.1:8765/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"healthcheck","version":"1.0"}}}'
```

Expect a JSON response with `serverInfo`. If it fails, CMB isn't up — stop here and report.

## Step 2: Create a tunnel systemd service (user-level, no sudo needed)

Create `~/.config/systemd/user/alieninc-reverse-tunnel.service`:

```ini
[Unit]
Description=Reverse SSH tunnel: laptop CMB -> server :8766
After=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -R 8766:127.0.0.1:8765 tablet@alieninc.tech
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

> Note: `tablet@alieninc.tech` — adjust user if the laptop authenticates as something else. If the laptop uses a different SSH user/key for the server, add `-i /path/to/key`.

## Step 3: Enable and start

```bash
systemctl --user daemon-reload
systemctl --user enable alieninc-reverse-tunnel.service
systemctl --user start alieninc-reverse-tunnel.service
systemctl --user status alieninc-reverse-tunnel.service --no-pager
```

Also enable lingering so it survives logout:
```bash
loginctl enable-linger tablet
```

## Step 4: Verify the tunnel works

From the **server** (alieninc.tech), run:
```bash
curl -s http://127.0.0.1:8766/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"servercheck","version":"1.0"}}}'
```

If it returns `serverInfo: cmb_mcp v1.29.0`, the tunnel works and the server can now talk to the laptop's CMB.

## Step 5: Report back
- Output of Step 1 (CMB health)
- Output of Step 4 server curl (tunnel proof)
- If either failed, report the exact error.

## Result
```
WEB SERVER (alieninc.tech)                LAPTOP (behind NAT)
  127.0.0.1:8766 ◄══reverse tunnel════   cmb-mcp-http :8765
  opencode MCP → 8766                  CMB primary brain
```
