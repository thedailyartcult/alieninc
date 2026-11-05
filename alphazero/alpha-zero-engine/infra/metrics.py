"""Dependency-free Prometheus metrics for the Alpha Zero engine.

Phase 11: Observability. Exposes a Prometheus-compatible ``/metrics`` text
endpoint for both the web app (Flask, gunicorn multi-worker) and the MCP
server (Streamable HTTP on :8020).

Design:

- ``registry`` — a process-local, thread-safe registry of counters, histograms
  and gauges. Records are labelled the same way as Prometheus series, e.g.
  ``alpha_zero_requests_total{endpoint=...,method=...,status=...}``.
- ``generate()`` — renders the registry plus aggregates derived from the shared
  on-disk analytics store (``infra.analytics``). Because the store is shared
  between gunicorn workers, the aggregate metrics reflect the whole process
  group even though counters are process-local.
- ``serve(port)`` — optional tiny HTTP server for stdio/standalone processes
  that have no HTTP surface of their own.

No third-party dependencies; the text format is emitted by hand so it works in
the Docker image, on the bare-metal server and inside CI.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

PREFIX = "alpha_zero"

# Seconds — aligned with typical web/MCP latency ranges.
HISTOGRAM_BUCKETS = [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]

# Gauge helper for process memory (Linux /proc/<pid>/statm).
_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096

_started_at = time.time()


def _rss_bytes() -> int:
    try:
        with open(f"/proc/{os.getpid()}/statm") as f:
            pages = int(f.read().split()[1])
        return pages * _PAGE_SIZE
    except (OSError, ValueError, IndexError):
        return 0


class MetricsRegistry:
    """Thread-safe Prometheus-style registry (counters / histograms / gauges)."""

    def __init__(self, prefix: str = PREFIX) -> None:
        self.prefix = prefix
        self._lock = threading.Lock()
        # (metric_name, labels_tuple) -> value
        self._counters: Dict[Tuple[str, Tuple[str, ...]], float] = {}
        self._gauges: Dict[Tuple[str, Tuple[str, ...]], float] = {}
        # (metric_name, labels_tuple) -> {"sum": float, "count": int, "buckets": [..]}
        self._histograms: Dict[Tuple[str, Tuple[str, ...]], dict] = {}

    # -- recording --------------------------------------------------------

    def counter(self, name: str, labels: Optional[dict] = None, amount: float = 1.0) -> None:
        key = (name, _labels(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def gauge(self, name: str, value: float, labels: Optional[dict] = None) -> None:
        key = (name, _labels(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def histogram(self, name: str, value: float, labels: Optional[dict] = None) -> None:
        key = (name, _labels(labels))
        with self._lock:
            entry = self._histograms.get(key)
            if entry is None:
                entry = {"sum": 0.0, "count": 0, "buckets": [0] * len(HISTOGRAM_BUCKETS)}
                self._histograms[key] = entry
            entry["sum"] += float(value)
            entry["count"] += 1
            for i, le in enumerate(HISTOGRAM_BUCKETS):
                if float(value) <= le:
                    entry["buckets"][i] += 1

    # -- rendering --------------------------------------------------------

    def render(self) -> str:
        lines: List[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{_fmt_labels(labels)} {_fmt(value)}")
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{_fmt_labels(labels)} {_fmt(value)}")
            for (name, labels), entry in sorted(self._histograms.items()):
                lines.append(f"# TYPE {name} histogram")
                for i, le in enumerate(HISTOGRAM_BUCKETS):
                    lines.append(f"{name}_bucket{{le=\"{_fmt(le)}\"}}{_fmt_labels(labels)} {entry['buckets'][i]}")
                lines.append(f"{name}_bucket{{le=\"+Inf\"}}{_fmt_labels(labels)} {entry['count']}")
                lines.append(f"{name}_sum{_fmt_labels(labels)} {_fmt(entry['sum'])}")
                lines.append(f"{name}_count{_fmt_labels(labels)} {entry['count']}")
        return "\n".join(lines)


def _labels(labels: Optional[dict]) -> Tuple[str, ...]:
    if not labels:
        return ()
    return tuple(f"{k}=\"{_escape(str(v))}\"" for k, v in sorted(labels.items()))


def _fmt_labels(labels: Tuple[str, ...]) -> str:
    return "{" + ",".join(labels) + "}" if labels else ""


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(round(float(value), 6))


# Module-level shared registry.
registry = MetricsRegistry()


# ---------------------------------------------------------------------------
# High-level recording helpers (used by api/routes.py and mcp_server.py)
# ---------------------------------------------------------------------------


def record_request(method: str, endpoint: str, status: int, duration_ms: float) -> None:
    """Record one HTTP request (web app)."""
    seconds = max(0.0, duration_ms / 1000.0)
    registry.counter(f"{PREFIX}_requests_total", {"endpoint": endpoint, "method": method, "status": str(status)})
    registry.histogram(f"{PREFIX}_request_duration_seconds", seconds, {"endpoint": endpoint})


def record_tool(tool: str, status: str, duration_ms: float) -> None:
    """Record one MCP tool call (engine MCP server)."""
    seconds = max(0.0, duration_ms / 1000.0)
    registry.counter(f"{PREFIX}_tool_calls_total", {"tool": tool, "status": status})
    registry.histogram(f"{PREFIX}_tool_duration_seconds", seconds, {"tool": tool})


def record_simulation(run_type: str, universes: int = 0, strategy: str = "", convergence: Optional[float] = None) -> None:
    """Record one simulation run (single / multiverse / branch / portfolio)."""
    labels = {"type": run_type}
    if strategy:
        labels["strategy"] = strategy
    registry.counter(f"{PREFIX}_simulation_runs_total", labels)
    if universes:
        registry.counter(f"{PREFIX}_universes_total", labels, amount=float(universes))
    if convergence is not None:
        registry.gauge(f"{PREFIX}_last_convergence_rate", float(convergence), {"type": run_type})


# ---------------------------------------------------------------------------
# Aggregates from the shared analytics store (all gunicorn workers combined)
# ---------------------------------------------------------------------------


def _analytics_metrics() -> List[str]:
    lines: List[str] = []
    try:
        from infra import analytics
        usage = analytics.usage_summary()
        sim = analytics.simulation_summary()
    except Exception:
        return lines

    total = usage.get("total_requests", 0)
    errors = usage.get("error_count", 0)
    lines.append("# TYPE alpha_zero_analytics_requests_total counter")
    lines.append(f"alpha_zero_analytics_requests_total {total}")
    lines.append("# TYPE alpha_zero_analytics_errors_total counter")
    lines.append(f"alpha_zero_analytics_errors_total {errors}")
    lines.append("# TYPE alpha_zero_analytics_error_rate gauge")
    lines.append(f"alpha_zero_analytics_error_rate {usage.get('error_rate', 0.0)}")
    for label, value in (("avg", usage.get("avg_latency_ms")), ("p50", usage.get("p50_latency_ms")), ("p95", usage.get("p95_latency_ms"))):
        lines.append("# TYPE alpha_zero_analytics_latency_ms gauge")
        lines.append(f"alpha_zero_analytics_latency_ms{{quantile=\"{label}\"}} {value}")
    for endpoint, count in sorted(usage.get("by_endpoint", {}).items()):
        lines.append(f"alpha_zero_analytics_requests_total{{endpoint=\"{_escape(endpoint)}\"}} {count}")
    lines.append("# TYPE alpha_zero_analytics_simulation_runs_total counter")
    lines.append(f"alpha_zero_analytics_simulation_runs_total {sim.get('total_runs', 0)}")
    lines.append("# TYPE alpha_zero_analytics_universes_total counter")
    lines.append(f"alpha_zero_analytics_universes_total {sim.get('total_universes', 0)}")
    if sim.get("avg_convergence") is not None:
        lines.append("# TYPE alpha_zero_analytics_avg_convergence gauge")
        lines.append(f"alpha_zero_analytics_avg_convergence {sim['avg_convergence']}")
    return lines


def _process_metrics() -> List[str]:
    lines = [
        "# TYPE alpha_zero_process_uptime_seconds gauge",
        f"alpha_zero_process_uptime_seconds {time.time() - _started_at:.2f}",
        "# TYPE alpha_zero_process_rss_bytes gauge",
        f"alpha_zero_process_rss_bytes {_rss_bytes()}",
    ]
    return lines


def generate() -> str:
    """Render the full Prometheus text payload for /metrics."""
    sections = [
        registry.render(),
        "\n".join(_analytics_metrics()),
        "\n".join(_process_metrics()),
    ]
    return "\n".join(s for s in sections if s) + "\n"


# ---------------------------------------------------------------------------
# Optional standalone HTTP server (stdio / headless processes)
# ---------------------------------------------------------------------------


def serve(port: int = 9100, host: str = "127.0.0.1") -> None:
    """Serve /metrics on a dedicated port in a background thread.

    Mirrors the CMB ``CMB_MONITOR_PORT`` pattern: expose Prometheus metrics for
    processes without their own HTTP surface.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server naming)
            if self.path.split("?")[0] != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            body = generate().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence request logging
            pass

    server = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="az-metrics").start()
    print(f"Alpha Zero metrics endpoint on http://{host}:{port}/metrics", flush=True)


def run_standalone() -> None:
    """CLI entrypoint: ``python -m infra.metrics --port 9100``."""
    import argparse

    parser = argparse.ArgumentParser(description="Alpha Zero Prometheus metrics exporter")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--print", action="store_true", help="print the payload once and exit")
    args = parser.parse_args()

    if args.print:
        print(generate(), end="")
        return
    serve(args.port)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_standalone()
