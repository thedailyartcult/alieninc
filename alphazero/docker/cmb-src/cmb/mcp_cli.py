"""Console entry for ``cmb-mcp``.

A thin shim so ``cmb-mcp --help`` renders WITHOUT the optional ``mcp``
dependency: ``cmb.mcp_server`` needs FastMCP at import time (tools register by
decorator at module scope), so the dependency gate fires on import — argparse must run
first, the import second. Keeps the actionable install hint either way."""
from __future__ import annotations

import argparse
import importlib.util
import sys


def _dependency_error() -> str:
    if sys.version_info < (3, 10):
        return (
            "The CMB MCP server requires Python 3.10 or newer.\n"
            "Create a Python 3.10+ environment, then run: pip install \"cmb[mcp]\""
        )
    if importlib.util.find_spec("mcp") is None:
        return (
            "The 'mcp' package is required to run the CMB MCP server.\n"
            "Install it with: pip install \"cmb[mcp]\""
        )
    return ""


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="cmb-mcp",
        description="Run the CMB MCP server over stdio - plugs CMB into "
                    "Claude Code, Cursor, Cline, Zed, and any MCP-capable client.",
        epilog="Configuration comes from the environment / .env (CMB_DB_PATH, "
               "CMB_WORKSPACES, ...). Generate a client config with: cmb-init",
    )
    ap.parse_args(argv)
    error = _dependency_error()
    if error:
        raise SystemExit(error)
    # Import AFTER argparse: raises a helpful SystemExit (with the pip install hint)
    # when the optional dependency is absent — see cmb/mcp_server.py.
    from cmb.mcp_server import main as run
    run()


if __name__ == "__main__":
    main()
