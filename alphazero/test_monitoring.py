"""Phase 7: Monitoring & analytics tests.

Covers the JSONL analytics store, the Flask monitoring endpoints
(/api/health, /api/analytics/*), request recording hooks, and the
dashboard Monitor tab.

Run:  python3 -m pytest test_monitoring.py -v
"""

import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(REPO_ROOT, "alpha-zero-engine")
sys.path.insert(0, ENGINE_DIR)


def _import_ok(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


NEEDS_FLASK = pytest.mark.skipif(
    not _import_ok("flask"),
    reason="flask not installed (pip install flask)",
)


def _import_analytics():
    from infra import analytics
    return analytics


# ---------------------------------------------------------------------------
# Analytics store
# ---------------------------------------------------------------------------


def test_store_record_and_summary(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    analytics.record_request("GET", "/api/portfolio/strategies", 200, 12.5)
    analytics.record_request("GET", "/api/portfolio/strategies", 200, 8.0)
    analytics.record_request("POST", "/api/multiverse", 200, 350.0)
    analytics.record_request("POST", "/api/does_not_exist", 404, 5.0)

    analytics.record_simulation("multiverse", {
        "name": "Player", "universes": 100, "strategy": "balanced",
        "convergence_rate": 0.82,
    })

    summary = analytics.summary()
    assert summary["requests"]["total_requests"] == 4
    assert summary["requests"]["error_count"] == 1
    assert summary["requests"]["error_rate"] == 0.25
    assert summary["requests"]["by_endpoint"]["/api/portfolio/strategies"] == 2
    assert summary["requests"]["by_status"]["404"] == 1
    assert summary["requests"]["p95_latency_ms"] >= summary["requests"]["p50_latency_ms"]

    assert summary["simulations"]["total_runs"] == 1
    assert summary["simulations"]["total_universes"] == 100
    assert summary["simulations"]["avg_convergence"] == 0.82
    assert summary["simulations"]["by_strategy"]["balanced"] == 1

    history = analytics.request_history(limit=2)
    assert len(history) == 2
    assert history[0]["endpoint"] == "/api/does_not_exist"


def test_store_capping(tmp_path, monkeypatch):
    analytics = _import_analytics()
    monkeypatch.setattr(analytics, "MAX_REQUESTS", 5)
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    for i in range(10):
        analytics.record_request("GET", f"/api/x/{i}", 200, 1.0)

    rows = analytics.request_history(limit=100)
    assert len(rows) == 5
    assert rows[0]["endpoint"] == "/api/x/9"


def test_store_reset(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.record_request("GET", "/api/x", 200, 1.0)
    assert analytics.usage_summary()["total_requests"] == 1
    analytics.reset()
    assert analytics.usage_summary()["total_requests"] == 0


# ---------------------------------------------------------------------------
# Flask web monitoring endpoints
# ---------------------------------------------------------------------------


def _web_app():
    from api.routes import create_app
    return create_app().test_client()


@NEEDS_FLASK
def test_health_endpoint(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    client = _web_app()
    r = client.get("/api/health")
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "ok"
    assert data["uptime_seconds"] > 0
    assert data["process"]["pid"] == os.getpid()
    assert set(data["dependencies"]) >= {"ollama", "redis", "alphacore_binary"}
    assert data["requests"]["total"] >= 0


@NEEDS_FLASK
def test_analytics_summary_endpoint(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    client = _web_app()
    client.get("/api/portfolio/strategies")

    r = client.get("/api/analytics/summary")
    data = r.get_json()
    assert r.status_code == 200
    assert data["requests"]["total_requests"] == 1
    assert data["requests"]["by_endpoint"]["/api/portfolio/strategies"] == 1
    assert "simulations" in data


@NEEDS_FLASK
def test_analytics_runs_endpoint(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    client = _web_app()
    r = client.get("/api/analytics/runs")
    assert r.status_code == 200
    assert r.get_json()["runs"] == []


@NEEDS_FLASK
def test_health_and_analytics_not_self_recorded(tmp_path):
    """Health/analytics requests do not pollute the request stream."""
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.reset()

    client = _web_app()
    client.get("/api/health")
    client.get("/api/analytics/summary")

    summary = analytics.usage_summary()
    assert summary["total_requests"] == 0


@NEEDS_FLASK
def test_dashboard_has_monitor_tab(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)

    client = _web_app()
    html = client.get("/").get_data(as_text=True)
    assert "tab-monitor" in html
    assert "btn-monitor-refresh" in html
    assert "monitor-runs-tbody" in html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_report(tmp_path):
    analytics = _import_analytics()
    analytics.set_data_dir(tmp_path)
    analytics.record_request("GET", "/api/test", 200, 1.0)

    import subprocess
    env = {
        "PYTHONPATH": ENGINE_DIR,
        "ALPHA_ZERO_ANALYTICS_DIR": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "infra.analytics", "--summary"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["requests"]["total_requests"] == 1
