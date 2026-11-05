#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Alpha Zero MCP Server Startup ==="
echo ""

# Install dependencies if needed
echo "[1/3] Checking dependencies..."
pip3 install --break-system-packages -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || true

# Start CMB backend data directory
echo "[2/3] Starting CMB backend..."
mkdir -p "$SCRIPT_DIR/cmb_data"

# Start MCP server in background
echo "[3/3] Starting Alpha Zero MCP Server (stdio mode)..."
cd "$SCRIPT_DIR"
python3 mcp_server.py &
MCP_PID=$!
echo "MCP Server PID: $MCP_PID"

# Also start HTTP mode on port 8000
python3 mcp_server.py --http --port 8000 &
MCP_HTTP_PID=$!
echo "MCP HTTP Server PID: $MCP_HTTP_PID"

echo ""
echo "=== Alpha Zero MCP Server is running ==="
echo "  stdio mode: PID $MCP_PID"
echo "  HTTP mode:  http://127.0.0.1:8000/mcp (PID $MCP_HTTP_PID)"
echo ""
echo "To stop: kill $MCP_PID $MCP_HTTP_PID"