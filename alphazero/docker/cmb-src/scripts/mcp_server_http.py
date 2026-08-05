#!/usr/bin/env python3
"""Persistent CMB MCP server (HTTP transport) — single DB owner.

Run ONE of these as a long-lived process so every Hermes session (gateway +
CLI) connects as a *client* instead of spawning its own stdio writer. This
removes the multi-writer SQLite WAL lock contention that caused intermittent
`database is locked` errors when more than one Hermes process opened the same
cmb.db file.

Usage:
    cmb-mcp-http                 # or: python -m scripts.mcp_server_http
    env CMB_HTTP_PORT=8711 python -m scripts.mcp_server_http

Transports:
    - streamable-http  on http://127.0.0.1:<port>/mcp   (default)
    - set CMB_HTTP_TRANSPORT=sse for /sse instead

Hermes config then uses:
    mcp_servers:
      cmb:
        url: http://127.0.0.1:8711/mcp
        # or transport: sse + url: http://127.0.0.1:8711/sse
"""
from __future__ import annotations

import os

from cmb.mcp_server import mcp  # reuse the existing tool bindings

HOST = os.environ.get("CMB_HTTP_HOST", "127.0.0.1")
PORT = int(os.environ.get("CMB_HTTP_PORT", "8711"))
TRANSPORT = os.environ.get("CMB_HTTP_TRANSPORT", "streamable-http")


def main() -> None:
    # CMB_DB_PATH is read by cmb.config.settings at service build
    # time (lazy, on first tool call) — same path the stdio server used.
    # FastMCP reads host/port from its settings object (not run()), so set them
    # here. This process is the *sole* writer to cmb.db.
    mcp.settings.host = HOST
    mcp.settings.port = PORT
    mcp.run(transport=TRANSPORT)


if __name__ == "__main__":
    main()
