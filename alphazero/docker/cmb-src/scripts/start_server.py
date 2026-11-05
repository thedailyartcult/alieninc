"""Launch the legacy CMB reference server with uvicorn."""
from __future__ import annotations

import argparse
import ipaddress
import os


def _port(value: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be from 1 to 65535")
    return port


def _loopback(host: str) -> bool:
    # Mirrors scripts/graph_server._loopback. An empty host binds ALL interfaces, so it
    # is emphatically not loopback; an unparseable hostname fails closed (token required).
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="cmb-server",
        description="Start the legacy CMB reference API server.",
    )
    ap.add_argument("--host", default=os.environ.get("CMB_HOST", "127.0.0.1"))
    ap.add_argument(
        "--port", type=_port,
        default=os.environ.get("PORT") or os.environ.get("CMB_PORT", "8700"),
    )
    ap.add_argument("--reload", action="store_true", help="Reload when source files change.")
    args = ap.parse_args(argv)
    # Fail at startup rather than silently publishing the memory API. The middleware in
    # cmb.app also refuses non-loopback peers without a token, but a container that
    # binds all interfaces should be told at boot, not once a request is refused.
    if not _loopback(args.host) and not os.environ.get("CMB_API_TOKEN", "").strip():
        ap.error("non-loopback serving requires CMB_API_TOKEN")
    os.environ["CMB_HOST"] = args.host
    os.environ["CMB_PORT"] = str(args.port)

    try:
        import uvicorn
        from cmb.config import settings
        from cmb.observability import configure_structured_logging
        if args.reload:
            app_target = "cmb.app:app"
        else:
            from cmb.app import app
            app_target = app
        structured_logs = configure_structured_logging()
    except (ImportError, ModuleNotFoundError):
        ap.exit(1, "Error: the server extra is required: pip install \"cmb[server]\""
                   " (needs Python 3.10+)\n")
    except (Exception, SystemExit):  # noqa: BLE001
        ap.exit(1, "Error: server initialization failed; run cmb-init --check\n")

    print(f"CMB - starting on {args.host}:{args.port}")
    print(f"  Database:     {settings.db_path}")
    print(f"  Embed model:  {settings.embed_model}")
    print(f"  LLM provider: {settings.llm_provider} / {settings.llm_model}")
    print(f"  Loop interval: {settings.loop_interval}s")
    print(f"  SDK base URL: {settings.base_url}")
    print(f"  OpenAPI:      {settings.base_url}/openapi.json")
    print()
    run_options = {
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
        # Keep the socket peer intact; CMB validates trusted forwarded headers and
        # the rightmost hop itself (see cmb.netutil.client_ip).
        "proxy_headers": False,
    }
    if structured_logs:
        # Preserve the redacting formatter installed by the app/launcher.
        run_options["log_config"] = None
    uvicorn.run(app_target, **run_options)


if __name__ == "__main__":
    main()
