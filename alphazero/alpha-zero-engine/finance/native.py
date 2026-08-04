"""Native core integration — Go-backed hot paths with pure-Python fallback.

Phase 4: Infrastructure. `alphacore` is a Go binary that bit-exactly ports the
finance hot paths (CPython-compatible MT19937 + cached Box-Muller gaussian,
MarketSimulator, Monte Carlo forecast, strategy comparison, stress tests).

Every function here first tries the native binary (json in / json out) and
falls back to the equivalent pure-Python implementation when the binary is
missing or fails. Callers receive identical result dicts either way; a
"backend" key reports which engine produced the result.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Optional

from finance.market import MarketSimulator
from finance.portfolio import PortfolioEngine, STRATEGIES
from finance.risk import RiskAnalyzer

_BINARY_CANDIDATES = [
    os.environ.get("ALPHA_CORE_BIN", ""),
    os.path.join(os.path.dirname(__file__), "..", "core", "bin", "alphacore"),
    os.path.join(os.path.dirname(__file__), "..", "core", "bin", "alphacore.exe"),
    shutil.which("alphacore") or "",
]


def _find_binary() -> Optional[str]:
    for candidate in _BINARY_CANDIDATES:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _call(command: str, payload: dict) -> Optional[dict]:
    """Run alphacore with a JSON payload; None on any failure."""
    binary = _find_binary()
    if binary is None:
        return None
    try:
        proc = subprocess.run(
            [binary, command],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout)
    except Exception:
        return None


def native_forecast(
    initial_value: float = 100000.0,
    strategy: str = "balanced",
    years: int = 10,
    paths: int = 1000,
    seed: int = 42,
) -> dict:
    """Monte Carlo forecast via the native core, falling back to Python."""
    strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
    payload = {
        "initial_value": initial_value,
        "expected_return": strat["expected_return"],
        "volatility": strat["volatility"],
        "years": years,
        "paths": paths,
        "seed": seed,
    }
    result = _call("forecast", payload)
    if result is not None:
        result["strategy"] = strategy
        result["strategy_name"] = strat["name"]
        result["backend"] = "go"
        return result
    result = RiskAnalyzer.monte_carlo_forecast(
        initial_value=initial_value, strategy=strategy,
        years=years, paths=paths, seed=seed,
    )
    result["backend"] = "python"
    return result


def native_market_years(
    seed: int = 42,
    years: int = 10,
    start_year: int = 2026,
) -> dict:
    """Market year series via the native core, falling back to Python."""
    result = _call("market", {
        "seed": seed, "years": years, "start_year": start_year, "series": True,
    })
    if result is not None:
        result["backend"] = "go"
        return result
    sim = MarketSimulator(seed=seed)
    market = sim.generate_series(start_year, start_year + years - 1)
    result = {
        "market": [
            {
                "year": m.year,
                "sp500_return": m.sp500_return,
                "bond_return": m.bond_return,
                "inflation": m.inflation,
                "fed_rate": m.fed_rate,
                "gdp_growth": m.gdp_growth,
                "unemployment": m.unemployment,
                "regime": m.regime,
            }
            for m in market
        ],
        "backend": "python",
    }
    return result


def native_compare_strategies(
    initial_value: float,
    years: int,
    market_returns: list[float],
    seed: int = 42,
) -> dict:
    """Strategy comparison via the native core, falling back to Python."""
    strategies = [
        {
            "name": name,
            "display_name": info["name"],
            "allocations": info["allocations"],
            "expected_return": info["expected_return"],
            "volatility": info["volatility"],
            "sharpe_target": info["sharpe_target"],
        }
        for name, info in STRATEGIES.items()
    ]
    result = _call("compare", {
        "initial_value": initial_value,
        "years": years,
        "market_returns": market_returns[:years],
        "strategies": strategies,
        "seed": seed,
    })
    if result is not None:
        result["backend"] = "go"
        return result
    result = PortfolioEngine.compare_strategies(
        initial_value, years, market_returns, seed=seed
    )
    result["backend"] = "python"
    return result


def native_stress_test(
    initial_value: float,
    strategy: str,
    seed: int = 42,
) -> dict:
    """Stress test via the native core, falling back to Python."""
    from finance.risk import STRESS_SCENARIOS
    strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
    result = _call("stress", {
        "initial_value": initial_value,
        "strategy": strategy,
        "allocations": strat["allocations"],
        "volatility": strat["volatility"],
        "scenarios": STRESS_SCENARIOS,
    })
    if result is not None:
        result["strategy_name"] = strat["name"]
        worst = min(result["scenarios"], key=lambda s: s["portfolio_shock"])
        result["worst_loss"] = round(initial_value * -worst["portfolio_shock"], 2)
        best = max(result["scenarios"], key=lambda s: s["portfolio_shock"])
        result["best_gain"] = round(initial_value * best["portfolio_shock"], 2)
        result["seed"] = seed
        result["backend"] = "go"
        return result
    result = RiskAnalyzer.stress_test(initial_value, strategy)
    result["seed"] = seed
    result["backend"] = "python"
    return result


def benchmark(
    paths: int = 10000,
    years: int = 30,
    rounds: int = 5,
    seed: int = 42,
) -> dict:
    """Benchmark the native core vs pure Python for the same workload."""
    result = _call("benchmark", {
        "seed": seed, "years": years, "paths": paths, "rounds": rounds,
        "initial_value": 100000.0,
    })
    if result is None:
        return {"backend": "unavailable", "reason": "alphacore binary not found"}

    start = time.monotonic()
    for _ in range(rounds):
        RiskAnalyzer.monte_carlo_forecast(
            initial_value=100000, strategy="balanced",
            years=years, paths=paths, seed=seed,
        )
    py_ms = (time.monotonic() - start) * 1000

    result["python_ms"] = round(py_ms, 2)
    result["speedup"] = round(py_ms / max(1, result["elapsed_ms"]), 1)
    result["backend"] = "go"
    return result
