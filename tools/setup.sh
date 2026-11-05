#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# Alien Inc — Hetzner Provisioning Script
# Run from the repo root on a fresh Ubuntu 24.04 CX22 instance
#   sudo bash tools/setup.sh
# ═══════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; exit 1; }

# ── Auto-detect paths ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONF="${APP_DIR}/nginx/alieninc.conf"

if [[ $(id -u) -ne 0 ]]; then
    err "This script must be run as root (sudo)."
fi

if [[ ! -f "${NGINX_CONF}" ]]; then
    err "NGINX config not found at ${NGINX_CONF}. Run from the repo root: sudo bash tools/setup.sh"
fi

# System user that will own the service (first non-root sudo user, or fallback)
SVC_USER="${SUDO_USER:-$(logname 2>/dev/null || echo 'ubuntu')}"
if [[ "$SVC_USER" == "root" ]]; then
    SVC_USER="ubuntu"
fi
log "Service will run as user: ${SVC_USER}"
log "App directory: ${APP_DIR}"

log "Updating system packages..."
apt update -qq && apt upgrade -y -qq

log "Installing dependencies..."
apt install -y -qq python3 python3-pip nginx ufw curl

log "Installing Node.js and Chromium (for compliance scanner)..."
if ! command -v node &>/dev/null; then
    apt install -y -qq nodejs npm || warn "Node.js install failed. WAT compliance scanner won't run."
fi
if ! command -v chromium &>/dev/null && ! command -v chromium-browser &>/dev/null; then
    apt install -y -qq chromium-browser 2>/dev/null || apt install -y -qq chromium 2>/dev/null || warn "Chromium install failed. Set CHROMIUM_PATH manually."
fi

log "Installing yfinance (for /api/competitors)..."
if pip3 install yfinance --break-system-packages -q 2>/dev/null; then
    log "yfinance installed successfully."
else
    warn "yfinance install failed. /api/competitors will return empty data."
    warn "Try: pip3 install yfinance --user, or set up a virtualenv."
fi

# ── NGINX ──────────────────────────────────────────────────
log "Configuring NGINX..."
cp "${NGINX_CONF}" /etc/nginx/sites-available/alieninc
ln -sf /etc/nginx/sites-available/alieninc /etc/nginx/sites-enabled/alieninc
rm -f /etc/nginx/sites-enabled/default

# Generate self-signed placeholder cert (so nginx can start)
# Replace with Cloudflare Origin CA cert after domain is set up
mkdir -p /etc/nginx/ssl
if [[ ! -f /etc/nginx/ssl/alieninc.pem ]]; then
    log "Generating self-signed placeholder SSL cert..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/alieninc.key \
        -out /etc/nginx/ssl/alieninc.pem \
        -subj "/C=GB/ST=London/L=London/O=AlienInc/CN=alieninc.tech" 2>/dev/null
    warn "Self-signed cert created. Replace with Cloudflare Origin CA cert after domain setup:"
    warn "  Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate"
    warn "  scp cert.pem → /etc/nginx/ssl/alieninc.pem"
    warn "  scp cert.key → /etc/nginx/ssl/alieninc.key"
fi

# Validate nginx config before starting
log "Validating NGINX config..."
if nginx -t 2>/dev/null; then
    log "NGINX config OK."
    systemctl enable --now nginx
else
    warn "NGINX config test failed. Check: nginx -t"
    warn "You may need to place SSL certs before starting nginx."
fi

# ── systemd ────────────────────────────────────────────────
log "Installing systemd service..."
cat > /etc/systemd/system/alieninc.service << SERVICE_EOF
[Unit]
Description=Alien Inc Server
After=network.target

[Service]
Type=simple
User=${SVC_USER}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable alieninc
systemctl start alieninc

sleep 2
if systemctl is-active --quiet alieninc; then
    log "alieninc.service is running."
else
    warn "alieninc.service failed to start. Check: journalctl -u alieninc -n 20"
fi

# ── Firewall ───────────────────────────────────────────────
log "Configuring firewall..."
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8080/tcp
ufw --force enable

log "Firewall status:"
ufw status verbose

echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Alien Inc provisioning complete.${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Replace self-signed cert with Cloudflare Origin CA certs"
echo "  2. Domain DNS: Cloudflare → alieninc.tech A → this server's IP"
echo "  3. Test: curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' -H 'Host: panteon.alieninc.tech' http://localhost:8080/"
echo "  4. View logs: journalctl -u alieninc -f"
