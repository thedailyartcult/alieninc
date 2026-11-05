"""Risk analytics — Value at Risk, expected shortfall, stress testing, Monte Carlo forecasts.

Phase 3: Algorithmic Portfolio Management. Quantifies downside risk for any
portfolio strategy and projects future value distributions with percentile bands.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Optional

from finance.portfolio import STRATEGIES, PortfolioEngine
from finance.market import MarketSimulator
from finance.metrics import compute_max_drawdown

# Per-asset-class shock multipliers for scenario stress tests
STRESS_SCENARIOS = {
    "2008_financial_crisis": {
        "cash": 0.02, "bonds": 0.05, "us_stocks": -0.55, "intl_stocks": -0.60,
        "real_estate": -0.35, "tech_stocks": -0.65, "leveraged_etf": -0.80,
        "crypto": -0.85, "emerging_markets": -0.65, "gold": 0.10,
        "consumer_staples": -0.20, "utilities": -0.15, "dividend_stocks": -0.40,
        "reits": -0.55, "preferred_stock": -0.25,
    },
    "dotcom_crash": {
        "cash": 0.03, "bonds": 0.08, "us_stocks": -0.45, "intl_stocks": -0.30,
        "real_estate": -0.10, "tech_stocks": -0.78, "leveraged_etf": -0.90,
        "crypto": -0.90, "emerging_markets": -0.40, "gold": 0.05,
        "consumer_staples": -0.05, "utilities": 0.02, "dividend_stocks": -0.15,
        "reits": -0.20, "preferred_stock": -0.10,
    },
    "stagflation": {
        "cash": 0.30, "bonds": -0.15, "us_stocks": -0.30, "intl_stocks": -0.35,
        "real_estate": -0.10, "tech_stocks": -0.40, "leveraged_etf": -0.50,
        "crypto": -0.45, "emerging_markets": -0.30, "gold": 0.25,
        "consumer_staples": -0.05, "utilities": 0.05, "dividend_stocks": -0.20,
        "reits": -0.15, "preferred_stock": -0.05,
    },
    "black_swan": {
        "cash": 0.05, "bonds": -0.30, "us_stocks": -0.55, "intl_stocks": -0.55,
        "real_estate": -0.45, "tech_stocks": -0.65, "leveraged_etf": -0.75,
        "crypto": -0.85, "emerging_markets": -0.60, "gold": -0.20,
        "consumer_staples": -0.35, "utilities": -0.30, "dividend_stocks": -0.45,
        "reits": -0.50, "preferred_stock": -0.35,
    },
    "hyper_growth": {
        "cash": 0.02, "bonds": 0.02, "us_stocks": 0.35, "intl_stocks": 0.30,
        "real_estate": 0.15, "tech_stocks": 0.60, "leveraged_etf": 0.90,
        "crypto": 1.50, "emerging_markets": 0.55, "gold": 0.10,
        "consumer_staples": 0.10, "utilities": 0.08, "dividend_stocks": 0.15,
        "reits": 0.20, "preferred_stock": 0.12,
    },
}


class RiskAnalyzer:
    """Downside risk quantification for portfolio strategies."""

    @staticmethod
    def compute_var(returns: list[float], confidence: float = 0.95) -> float:
        """
        Historical Value at Risk: the worst loss at the given confidence level.

        Returns a negative number (e.g., -0.12 means 12% worst-case loss).
        """
        if not returns:
            return 0.0
        confidence = max(0.5, min(0.999, float(confidence)))
        sorted_returns = sorted(returns)
        index = int((1 - confidence) * len(sorted_returns))
        index = max(0, min(len(sorted_returns) - 1, index))
        return round(sorted_returns[index], 4)

    @staticmethod
    def expected_shortfall(returns: list[float], confidence: float = 0.95) -> float:
        """Conditional VaR: average loss beyond the VaR threshold."""
        if not returns:
            return 0.0
        confidence = max(0.5, min(0.999, float(confidence)))
        sorted_returns = sorted(returns)
        tail_size = max(1, int((1 - confidence) * len(sorted_returns)))
        tail = sorted_returns[:tail_size]
        return round(sum(tail) / len(tail), 4)

    @staticmethod
    def compute_max_drawdown(values: list[float]) -> float:
        """Re-export of max drawdown for portfolio value series."""
        return round(compute_max_drawdown(values), 4)

    @classmethod
    def stress_test(cls, initial_value: float, strategy: str) -> dict:
        """Apply stress scenarios to a strategy's allocations."""
        strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
        allocations = strat["allocations"]
        volatility = strat["volatility"]

        results = []
        for scenario, shocks in STRESS_SCENARIOS.items():
            portfolio_shock = 0.0
            for asset, weight in allocations.items():
                shock = shocks.get(asset, -0.2)
                portfolio_shock += weight * shock
            affected_value = initial_value * (1 + portfolio_shock)
            results.append({
                "scenario": scenario,
                "portfolio_shock": round(portfolio_shock, 4),
                "value_after": round(affected_value, 2),
                "loss": round(initial_value - affected_value, 2),
            })

        results.sort(key=lambda r: r["portfolio_shock"])
        worst = results[0]
        best = results[-1]

        return {
            "strategy": strategy,
            "strategy_name": strat["name"],
            "initial_value": initial_value,
            "volatility": volatility,
            "scenarios": results,
            "worst_scenario": worst["scenario"],
            "worst_loss": round(initial_value * -worst["portfolio_shock"], 2),
            "best_scenario": best["scenario"],
            "best_gain": round(initial_value * best["portfolio_shock"], 2),
        }

    @classmethod
    def monte_carlo_forecast(
        cls,
        initial_value: float = 100000.0,
        strategy: str = "balanced",
        years: int = 10,
        paths: int = 1000,
        seed: int = 42,
    ) -> dict:
        """
        Monte Carlo forecast of portfolio value over N years.

        Each path compounds annual returns = market regime return (from the
        deterministic MarketSimulator) scaled by the strategy's sensitivity,
        plus strategy-specific noise. Returns percentile bands.
        """
        strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
        volatility = strat["volatility"]
        expected = strat["expected_return"]
        market_sim = MarketSimulator(seed=seed)
        rng = random.Random(seed)

        final_values = []
        annual_series: list[list[float]] = []
        for _ in range(max(10, int(paths))):
            value = initial_value
            series = [value]
            for i in range(max(1, int(years))):
                year = 2026 + i
                market_return = market_sim.get_year_return(year)
                # Blend market regime with strategy alpha
                strategy_return = market_return * (expected / 0.10) + rng.gauss(0, volatility * 0.3)
                value *= (1 + strategy_return)
                value = max(0.0, value)
                series.append(round(value, 2))
            final_values.append(value)
            annual_series.append(series)

        percentiles = {}
        for pct in (5, 25, 50, 75, 95):
            idx = int((pct / 100.0) * (len(final_values) - 1))
            percentiles[f"p{pct}"] = round(sorted(final_values)[idx], 2)

        mean_value = statistics.mean(final_values)
        median_value = statistics.median(final_values)
        prob_loss = sum(1 for v in final_values if v < initial_value) / len(final_values)

        return {
            "initial_value": initial_value,
            "strategy": strategy,
            "strategy_name": strat["name"],
            "years": int(years),
            "paths": len(final_values),
            "seed": seed,
            "percentiles": percentiles,
            "mean_value": round(mean_value, 2),
            "median_value": round(median_value, 2),
            "prob_of_loss": round(prob_loss, 4),
            "worst_path": round(min(final_values), 2),
            "best_path": round(max(final_values), 2),
            "median_return_pct": round((median_value / initial_value - 1) * 100, 2),
        }
