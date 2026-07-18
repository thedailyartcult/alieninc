#!/usr/bin/env bash
# =============================================================================
# Hawksight Engine — Setup & Launch Script
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════╗"
echo "║  HAWKSIGHT Engine — Setup & Launch                  ║"
echo "║  Vulnerability Scanner for Alien Inc.               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 is required but not found."
    exit 1
fi

PYTHON_VER=$(python3 --version 2>&1)
echo "[*] Using: $PYTHON_VER"

# Create virtualenv if needed
if [ ! -d "$ENGINE_DIR/.venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv "$ENGINE_DIR/.venv"
fi

# Activate
source "$ENGINE_DIR/.venv/bin/activate"

# Install dependencies
echo "[*] Installing dependencies..."
pip install -q -r "$ENGINE_DIR/requirements.txt" 2>/dev/null

# Create data directory
mkdir -p "$ENGINE_DIR/data"

echo ""
echo "[*] Starting Hawksight Engine on http://0.0.0.0:8721"
echo "[*] Login page: http://localhost:8721/login"
echo "[*] Scan page:  http://localhost:8721/scan"
echo "[*] Default credentials:"
echo "    Username: admin"
echo "    Password: hawksight2026"
echo ""
echo "[*] Press Ctrl+C to stop"
echo ""

cd "$ENGINE_DIR"
python3 main.py
