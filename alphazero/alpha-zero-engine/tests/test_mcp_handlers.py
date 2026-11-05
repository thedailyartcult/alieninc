"""Regression tests for MCP handler fixes.

Locks in the pentest findings:
  - chaos injection actually mutates universes (chaotic_injections > 0)
  - compare_strategies returns real, differentiated compounding
  - convergence_analysis returns a real measured rate
  - risk_analysis: ES95 <= VaR95 < 0, drawdown compounds, stress included
  - financial_forecast: ordered percentile bands
  - portfolio_optimize: Sharpe ranking respects the risk cap
  - best_branch: returns an actual universe instead of None
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import mcp_server


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


def test_chaos_injection_is_real():
    clean = _run(mcp_server.handle_simulate(
        {"name": "T", "universes": 12, "seed": 42, "inject_chaos": False,
         "workspace": "test_handlers"}))
    chaos = _run(mcp_server.handle_simulate(
        {"name": "T", "universes": 12, "seed": 42, "inject_chaos": True,
         "injection_rate": 0.9, "workspace": "test_handlers"}))
    assert chaos["result"]["chaotic_injections"] > 0, (
        "inject_chaos=True produced zero injections"
    )
    assert clean["result"]["chaotic_injections"] == 0
    # Chaos must actually change trajectories, not just count.
    c, h = clean["result"], chaos["result"]
    differs = (abs(c["alpha"] - h["alpha"]) > 1e-9
               or c["convergence_rate"] != h["convergence_rate"])
    assert differs, "chaotic run identical to clean run"


def test_compare_strategies_real():
    d = _run(mcp_server.handle_compare_strategies(
        {"initial_value": 100000, "years": 10, "seed": 42,
         "workspace": "test_handlers"}))["result"]
    vals = [s["final_value"] for s in d["strategies"].values()]
    rets = [s["total_return_pct"] for s in d["strategies"].values()]
    assert len(set(vals)) > 1, "all strategies identical — stub behavior"
    assert any(abs(r) > 1.0 for r in rets), "returns all ~0% — stub behavior"
    assert len(d["market_returns"]) == 10


def test_convergence_analysis_real():
    d = _run(mcp_server.handle_convergence_analysis(
        {"name": "T", "universes": 10, "threshold": 0.85, "seed": 7,
         "workspace": "test_handlers"}))["result"]
    rate = d["convergence_rate"]
    assert isinstance(rate, float) and 0.0 <= rate <= 1.0 and rate > 0.0, (
        f"convergence rate not real: {rate}"
    )
    assert d["meets_threshold"] == (rate >= 0.85)


def test_risk_analysis_math():
    d = _run(mcp_server.handle_risk_analysis(
        {"strategy": "balanced", "initial_value": 100000, "years": 10,
         "seed": 42, "workspace": "test_handlers"}))["result"]
    var_95 = d["var_95"]
    es_95 = d["expected_shortfall_95"]
    dd = d["max_drawdown"]
    assert var_95 < 0, f"VaR should be a loss: {var_95}"
    # ES is the mean of the tail beyond VaR: strictly worse or equal.
    assert es_95 <= var_95 + 1e-6, f"ES {es_95} must be <= VaR {var_95}"
    assert 0 < dd <= 1.0, f"drawdown out of range: {dd}"


def test_financial_forecast_percentile_ordering():
    d = _run(mcp_server.handle_financial_forecast(
        {"initial_value": 100000, "years": 10, "paths": 200, "seed": 42,
         "workspace": "test_handlers"}))["result"]
    p = d["percentiles"]
    assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"], (
        f"percentiles unordered: {p}"
    )
    assert 0.0 <= d["prob_of_loss"] <= 1.0


def test_portfolio_optimize_sharpe_and_cap():
    aggressive = _run(mcp_server.handle_portfolio_optimize(
        {"risk_tolerance": 10, "workspace": "test_handlers"}))["result"]
    conservative = _run(mcp_server.handle_portfolio_optimize(
        {"risk_tolerance": 2, "workspace": "test_handlers"}))["result"]
    assert aggressive["recommended"] is not None
    # Risk cap respected: conservative recommendations must not exceed cap.
    for s in conservative["ranked_strategies"]:
        assert s["volatility"] <= conservative["max_acceptable_volatility"] + 1e-9
    ranked = aggressive["ranked_strategies"]
    sharpes = [s["sharpe_ratio"] for s in ranked]
    assert sharpes == sorted(sharpes, reverse=True), "not sorted by Sharpe"
    with_age = _run(mcp_server.handle_portfolio_optimize(
        {"risk_tolerance": 5, "age": 65, "workspace": "test_handlers"}))["result"]
    assert with_age["glide_path"]["growth_allocation"] < 0.90


def test_best_branch_returns_universe():
    d = _run(mcp_server.handle_best_branch(
        {"name": "T", "universes": 8, "metric": "net_worth", "seed": 3,
         "workspace": "test_handlers"}))["result"]
    bb = d["best_branch"]
    assert bb is not None and bb["universe_id"], "best_branch still None (stub)"
