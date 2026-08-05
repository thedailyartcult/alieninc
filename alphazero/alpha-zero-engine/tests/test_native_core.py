"""Parity tests: native Go core must match pure-Python finance outputs.

Phase 4: Infrastructure. The Go `alphacore` binary ports the finance hot
paths with a CPython-compatible RNG (MT19937 + cached Box-Muller gaussian),
so results should be bit-identical or within float tolerance.
"""

import json
import math
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from finance.market import MarketSimulator
from finance.native import (
    _find_binary,
    native_advisor,
    native_compare_strategies,
    native_forecast,
    native_market_years,
    native_stress_test,
)
from finance.portfolio import PortfolioEngine, STRATEGIES
from finance.risk import RiskAnalyzer

NEEDS_BINARY = pytest.mark.skipif(
    _find_binary() is None,
    reason="alphacore binary not built (run core/scripts/build_core.sh)",
)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


@NEEDS_BINARY
@pytest.mark.parametrize("seed", [1, 7, 42, 99, 1234])
def test_forecast_parity(seed):
    go = native_forecast(initial_value=100000, strategy="balanced",
                         years=10, paths=500, seed=seed)
    py = RiskAnalyzer.monte_carlo_forecast(initial_value=100000, strategy="balanced",
                                           years=10, paths=500, seed=seed)
    assert go["backend"] == "go"
    assert close(go["mean_value"], py["mean_value"])
    assert close(go["median_value"], py["median_value"])
    assert close(go["prob_of_loss"], py["prob_of_loss"])
    assert close(go["worst_path"], py["worst_path"])
    assert close(go["best_path"], py["best_path"])
    for pct in ("p5", "p25", "p50", "p75", "p95"):
        assert close(go["percentiles"][pct], py["percentiles"][pct]), pct


@NEEDS_BINARY
@pytest.mark.parametrize("seed", [0, 42, 2026])
def test_market_parity(seed):
    go = native_market_years(seed=seed, years=20)
    assert go["backend"] == "go"
    sim = MarketSimulator(seed=seed)
    py = sim.generate_series(2026, 2026 + 19)
    assert len(go["market"]) == len(py)
    for g, p in zip(go["market"], py):
        assert g["year"] == p.year
        assert g["regime"] == p.regime
        for key in ("sp500_return", "bond_return", "inflation", "fed_rate",
                    "gdp_growth", "unemployment"):
            assert close(g[key], p.__dict__[key], tol=1e-6), (seed, p.year, key)


@NEEDS_BINARY
@pytest.mark.parametrize("seed", [1, 42, 777])
def test_compare_parity(seed):
    market_sim = MarketSimulator(seed=seed)
    market_returns = [market_sim.get_year_return(2026 + i) for i in range(10)]
    go = native_compare_strategies(100000, 10, market_returns, seed=seed)
    py = PortfolioEngine.compare_strategies(100000, 10, market_returns, seed=seed)
    assert go["backend"] == "go"
    assert set(go["results"].keys()) == set(py.keys())
    for name, gy in go["results"].items():
        pv = py[name]
        assert close(gy["final_value"], pv["final_value"], tol=1e-9), name
        assert close(gy["total_return_pct"], pv["total_return_pct"], tol=1e-9), name
        assert close(gy["annualized_return_pct"], pv["annualized_return_pct"], tol=1e-9), name


@NEEDS_BINARY
@pytest.mark.parametrize("strategy", ["balanced", "hyper_growth", "recession_defense", "dividend_income"])
def test_stress_parity(strategy):
    go = native_stress_test(100000, strategy, seed=7)
    py = RiskAnalyzer.stress_test(100000, strategy)
    assert go["backend"] == "go"
    assert len(go["scenarios"]) == len(py["scenarios"])
    for g, p in zip(go["scenarios"], py["scenarios"]):
        assert g["scenario"] == p["scenario"]
        assert close(g["portfolio_shock"], p["portfolio_shock"], tol=1e-9)
        assert close(g["value_after"], p["value_after"], tol=1e-6)
        assert close(g["loss"], p["loss"], tol=1e-6)
    assert close(go["worst_loss"], py["worst_loss"], tol=1e-6)


@NEEDS_BINARY
def test_forecast_uses_binary_and_matches_many_seeds():
    for seed in range(20):
        go = native_forecast(initial_value=50000, strategy="hyper_growth",
                             years=5, paths=100, seed=seed)
        py = RiskAnalyzer.monte_carlo_forecast(initial_value=50000, strategy="hyper_growth",
                                               years=5, paths=100, seed=seed)
        assert go["backend"] == "go"
        assert close(go["median_value"], py["median_value"]), seed


@NEEDS_BINARY
def test_benchmark_reports_speedup():
    result = native_forecast  # noqa: F841  (import sanity)
    out = subprocess.run(
        [_find_binary(), "benchmark"],
        input=json.dumps({"seed": 42, "years": 30, "paths": 2000, "rounds": 2,
                          "initial_value": 100000}).encode(),
        capture_output=True,
    )
    data = json.loads(out.stdout)
    assert data["runs"] == 4000
    assert data["elapsed_ms"] > 0


# ── Phase 8 advisor parity (Go alphacore vs Python AI agents) ─────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("OLLAMA_DISABLE", "1")


def _without_backend(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "backend"}

_ADVISOR_CASES = {
    "standard": {
        "name": "Alex", "age": 32, "gender": "male", "happiness": 60, "health": 75,
        "smarts": 65, "looks": 60, "karma": 70, "money": 12000.0, "portfolio_value": 45000.0,
        "debt": 3000.0, "occupation": "Software Engineer", "education_level": "bachelors",
    },
    "debt_burdened": {
        "name": "Riya", "age": 41, "gender": "female", "happiness": 40, "health": 55,
        "smarts": 70, "looks": 50, "karma": 60, "money": -15000.0, "portfolio_value": 8000.0,
        "debt": 60000.0, "occupation": "Teacher", "education_level": "masters",
    },
    "retiree": {
        "name": "Ken", "age": 67, "gender": "male", "happiness": 80, "health": 65,
        "smarts": 55, "looks": 45, "karma": 75, "money": 200000.0, "portfolio_value": 450000.0,
        "debt": 0.0, "occupation": "Retired", "education_level": "high_school",
    },
    "zero_attributes": {
        "name": "Zero", "age": 0, "gender": "unknown", "happiness": 0, "health": 0,
        "smarts": 0, "looks": 0, "karma": 0, "money": 0.0, "portfolio_value": 0.0,
        "debt": 0.0, "occupation": "unknown", "education_level": "none",
    },
    "missing_fields": {
        "name": "Mystery", "age": 28,
    },
}


@NEEDS_BINARY
@pytest.mark.parametrize("kind", ["financial", "health", "mentor"])
@pytest.mark.parametrize("case_name", sorted(_ADVISOR_CASES))
def test_advisor_parity(kind, case_name):
    from ai.financial_advisor import FinancialAdvisorAgent
    from ai.health_coach import HealthCoachAgent
    from ai.mentor import MentorAgent

    char = _ADVISOR_CASES[case_name]
    go = native_advisor(kind, char)
    assert go["backend"] == "go", f"{kind}/{case_name} fell back to Python"

    if kind == "financial":
        py = FinancialAdvisorAgent().provide_advice(char, "general")
    elif kind == "health":
        py = HealthCoachAgent().provide_advice(char, "general")
    else:
        py = MentorAgent().provide_mentorship(char, "")

    if kind == "mentor":
        # The full LifeCoachAgent is Python-only; Go produces an explicit
        # baseline block (message marker) that the Rust client replaces.
        go_body = {k: v for k, v in go.items() if k != "life_coach"}
        py_body = {k: v for k, v in py.items() if k != "life_coach"}
        assert _without_backend(go_body) == py_body, \
            f"Go != Python for advisor {kind} case {case_name} (excluding life_coach)"
        assert go["life_coach"]["character_name"] == py["life_coach"]["character_name"]
        assert "baseline" in go["life_coach"].get("message", "")
    else:
        assert _without_backend(go) == py, f"Go != Python for advisor {kind} case {case_name}"


@NEEDS_BINARY
@pytest.mark.parametrize("kind", ["financial", "health", "mentor"])
def test_advisor_parity_with_prior_advice(kind):
    from ai.financial_advisor import FinancialAdvisorAgent
    from ai.health_coach import HealthCoachAgent
    from ai.mentor import MentorAgent

    char = dict(_ADVISOR_CASES["standard"])
    char["prior_advice"] = [
        "Saved three months of expenses and started investing.",
        "Started automatic transfers into a diversified index fund.",
    ]

    go = native_advisor(kind, char)
    assert go["backend"] == "go"
    assert go["continuity"]["prior_advice_recalled"] == char["prior_advice"]

    if kind == "financial":
        py = FinancialAdvisorAgent().provide_advice(char, "general")
    elif kind == "health":
        py = HealthCoachAgent().provide_advice(char, "general")
    else:
        py = MentorAgent().provide_mentorship(char, "")

    if kind == "mentor":
        go_body = {k: v for k, v in go.items() if k != "life_coach"}
        py_body = {k: v for k, v in py.items() if k != "life_coach"}
        assert _without_backend(go_body) == py_body
    else:
        assert _without_backend(go) == py


@NEEDS_BINARY
@pytest.mark.parametrize("situation", ["retirement", "debt", "general"])
def test_financial_advisor_situation_variants(situation):
    from ai.financial_advisor import FinancialAdvisorAgent

    char = _ADVISOR_CASES["standard"]
    go = native_advisor("financial", char, situation=situation)
    assert go["backend"] == "go"
    py = FinancialAdvisorAgent().provide_advice(char, situation)
    assert _without_backend(go) == py


# ── TiDB persistence via native core ──────────────────────────────────────

def _sql_store_ready() -> bool:
    """True when a MySQL-compatible server (TiDB) answers on the DSN."""
    from infra import tidb_store
    return tidb_store.healthy()


@pytest.mark.skipif(not _sql_store_ready(), reason="no TiDB/MySQL server on DSN")
def test_report_store_load_roundtrip_go():
    from finance.native import native_report
    rid = "go_pytest_report_1"
    stored = native_report("store", report_id=rid, run_type="multiverse",
                           config={"universes": 10, "seed": 7},
                           report={"convergence_rate": 0.92}, backend="go")
    assert stored.get("backend") == "go"
    assert stored.get("stored") is True
    loaded = native_report("load", report_id=rid)
    assert loaded.get("found") is True
    assert loaded["report"]["convergence_rate"] == 0.92


@pytest.mark.skipif(not _sql_store_ready(), reason="no TiDB/MySQL server on DSN")
def test_report_list_go():
    from finance.native import native_report
    native_report("store", report_id="go_pytest_report_2", run_type="forecast",
                  config={"years": 3}, report={"p50": 555}, backend="go")
    listed = native_report("list", limit=50)
    assert listed.get("backend") == "go"
    ids = [r["id"] for r in listed.get("results", [])]
    assert "go_pytest_report_2" in ids
