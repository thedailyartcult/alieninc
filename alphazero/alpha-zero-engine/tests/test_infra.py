"""Infrastructure tests — Redis cache layer and TiDB-compatible persistence.

Phase 4: Infrastructure. Cache tests need Redis on 127.0.0.1:6379 (skipped
otherwise). Store tests need any MySQL-compatible server (MariaDB/MySQL/
TiDB); the DSN is controlled by ALPHA_ZERO_SQL_DSN, defaulting to the local
MariaDB during development.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ALPHA_ZERO_SQL_DSN", "mysql://root@127.0.0.1:3306/alpha_zero")

from infra import cache, tidb_store  # noqa: E402


# ── Redis cache ───────────────────────────────────────────────────────────

def test_config_hash_is_stable():
    h1 = cache.config_hash(42, "balanced", 10, 1000)
    h2 = cache.config_hash(42, "balanced", 10, 1000)
    h3 = cache.config_hash(43, "balanced", 10, 1000)
    assert h1 == h2
    assert h1 != h3


def test_get_set_roundtrip():
    cache.clear()
    key = "alpha_zero:test:roundtrip"
    cache.set(key, {"value": 123, "nested": [1, 2, 3]})
    value = cache.get(key)
    assert value is not None
    assert value["value"] == 123
    cache.clear()


def test_missing_key_returns_none():
    cache.clear()
    assert cache.get("alpha_zero:test:missing") is None


def test_cached_produces_once():
    cache.clear()
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return {"seq": calls["n"]}

    v1, s1 = cache.cached("alpha_zero:test:producer", producer)
    v2, s2 = cache.cached("alpha_zero:test:producer", producer)
    assert v1["seq"] == v2["seq"] == 1
    assert s1 == "computed"
    assert s2 == "cache"
    assert calls["n"] == 1
    cache.clear()


def test_universe_snapshot_roundtrip():
    cache.clear()
    state = {"age": 25, "health": 80, "events": ["job_promotion"]}
    assert cache.save_universe("u_test_1", state)
    loaded = cache.load_universe("u_test_1")
    assert loaded == state
    cache.clear()


def test_run_log():
    cache.clear()
    cache.log_run("multiverse", {"universes": 10}, {"convergence_rate": 0.5})
    runs = cache.recent_runs(5)
    assert runs and runs[0]["type"] == "multiverse"
    cache.clear()


# ── TiDB-compatible store ─────────────────────────────────────────────────

@pytest.mark.skipif(not tidb_store.healthy(), reason="no MySQL-compatible server on DSN")
def test_bootstrap_and_roundtrip():
    assert tidb_store.bootstrap_schema()
    ok = tidb_store.save_report(
        "test_report_1", "multiverse",
        {"universes": 5}, {"convergence_rate": 0.9}, backend="go",
    )
    assert ok
    report = tidb_store.load_report("test_report_1")
    assert report is not None
    assert report["convergence_rate"] == 0.9


@pytest.mark.skipif(not tidb_store.healthy(), reason="no MySQL-compatible server on DSN")
def test_universe_persistence():
    assert tidb_store.bootstrap_schema()
    assert tidb_store.save_universe("u_persist_1", "Player", 25, {"money": 5000})
    loaded = tidb_store.load_universe("u_persist_1")
    assert loaded is not None
    assert loaded["money"] == 5000


@pytest.mark.skipif(not tidb_store.healthy(), reason="no MySQL-compatible server on DSN")
def test_list_and_metrics():
    assert tidb_store.bootstrap_schema()
    tidb_store.save_report(
        "test_report_2", "forecast",
        {"years": 5}, {"percentiles": {"p50": 123456}}, backend="go",
    )
    reports = tidb_store.list_reports("forecast")
    assert any(r["id"] == "test_report_2" for r in reports)
    metrics = tidb_store.recent_run_metrics("forecast", hours=24)
    assert metrics is not None
    assert metrics["count"] >= 1
