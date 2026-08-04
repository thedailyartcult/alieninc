"""Portfolio optimizer — risk-tolerance allocation, lifecycle glide paths, efficient frontier.

Phase 3: Algorithmic Portfolio Management. Provides mean-variance-style scoring over
candidate allocations, age-based target-date glide paths, and an efficient frontier sweep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from finance.portfolio import STRATEGIES

# Annual expected return / volatility per asset class (deterministic model inputs)
ASSET_PROFILES = {
    "cash": {"expected_return": 0.025, "volatility": 0.01},
    "bonds": {"expected_return": 0.045, "volatility": 0.06},
    "us_stocks": {"expected_return": 0.09, "volatility": 0.15},
    "intl_stocks": {"expected_return": 0.085, "volatility": 0.17},
    "real_estate": {"expected_return": 0.07, "volatility": 0.12},
    "tech_stocks": {"expected_return": 0.12, "volatility": 0.25},
    "leveraged_etf": {"expected_return": 0.15, "volatility": 0.40},
    "crypto": {"expected_return": 0.18, "volatility": 0.60},
    "emerging_markets": {"expected_return": 0.10, "volatility": 0.22},
    "gold": {"expected_return": 0.04, "volatility": 0.15},
    "consumer_staples": {"expected_return": 0.055, "volatility": 0.08},
    "utilities": {"expected_return": 0.05, "volatility": 0.09},
    "dividend_stocks": {"expected_return": 0.06, "volatility": 0.10},
    "reits": {"expected_return": 0.065, "volatility": 0.14},
    "preferred_stock": {"expected_return": 0.05, "volatility": 0.11},
}

RISK_FREE_RATE = 0.02
# Fixed pairwise asset correlation for variance estimation (realism; avoids
# the independence assumption that overstates diversification benefits)
ASSET_CORRELATION = 0.30


@dataclass
class AllocationOption:
    """A scored candidate allocation."""

    name: str
    allocations: dict
    expected_return: float
    volatility: float
    sharpe_ratio: float
    rationale: str


class PortfolioOptimizer:
    """Algorithmic allocation optimization for the Alpha Zero finance engine."""

    @staticmethod
    def _score(allocations: dict) -> tuple:
        """Return (expected_return, volatility, sharpe) for an allocation dict."""
        names = [a for a in allocations if allocations[a] > 0]
        expected_return = 0.0
        for asset in names:
            profile = ASSET_PROFILES.get(asset, {"expected_return": 0.06, "volatility": 0.12})
            expected_return += allocations[asset] * profile["expected_return"]

        # Variance with a fixed pairwise correlation: preserves the
        # diversification effect without a full correlation matrix.
        variance = 0.0
        for a in names:
            pa = ASSET_PROFILES.get(a, {"expected_return": 0.06, "volatility": 0.12})
            wav = allocations[a] * pa["volatility"]
            variance += wav * wav
            for b in names:
                if b <= a:
                    continue
                pb = ASSET_PROFILES.get(b, {"expected_return": 0.06, "volatility": 0.12})
                variance += 2 * ASSET_CORRELATION * allocations[a] * pa["volatility"] * allocations[b] * pb["volatility"]

        volatility = math.sqrt(max(0.0, variance))
        sharpe = (expected_return - RISK_FREE_RATE) / volatility if volatility > 0 else 0.0
        return expected_return, volatility, sharpe

    @classmethod
    def _blend(cls, a: dict, b: dict, ratio: float) -> dict:
        """Blend two allocations: result = a*ratio + b*(1-ratio)."""
        merged = {}
        for asset in set(a) | set(b):
            merged[asset] = a.get(asset, 0.0) * ratio + b.get(asset, 0.0) * (1 - ratio)
        return {k: round(v, 4) for k, v in merged.items() if v > 0.001}

    @classmethod
    def _candidate_pool(cls) -> list[tuple]:
        """Build candidate allocations: base strategies plus pairwise blends."""
        strategies = list(STRATEGIES.values())
        candidates = [(s["name"], dict(s["allocations"])) for s in strategies]
        for i in range(len(strategies)):
            for j in range(i + 1, len(strategies)):
                for ratio in (0.25, 0.5, 0.75):
                    candidates.append(
                        (
                            f"{strategies[i]['name']} × {strategies[j]['name']} ({int(ratio*100)}/{(100-int(ratio*100))})",
                            cls._blend(strategies[i]["allocations"], strategies[j]["allocations"], ratio),
                        )
                    )
        return candidates

    @classmethod
    def optimize(cls, risk_tolerance: int = 5) -> dict:
        """
        Find the optimal allocation for a risk tolerance 0 (very safe) to 10 (aggressive).

        Scores all candidate allocations (strategies + blends) by Sharpe ratio,
        constrained by a volatility cap derived from the risk tolerance.
        """
        risk_tolerance = max(0, min(10, int(risk_tolerance)))
        volatility_cap = 0.03 + risk_tolerance * 0.05  # tol 0 -> 3%, tol 10 -> 53%

        scored = []
        for name, allocations in cls._candidate_pool():
            expected_return, volatility, sharpe = cls._score(allocations)
            scored.append((name, allocations, expected_return, volatility, sharpe))

        scored.sort(key=lambda x: x[4], reverse=True)
        eligible = [s for s in scored if s[3] <= volatility_cap]
        if eligible:
            eligible.sort(key=lambda x: x[4], reverse=True)
            top3 = eligible[:3]
        else:
            # Nothing meets the cap: pick the safest available allocation
            safest = min(scored, key=lambda x: x[3])
            top3 = [safest]
        best = top3[0]

        if risk_tolerance <= 2:
            label = "conservative (wealth preservation)"
        elif risk_tolerance <= 4:
            label = "moderately conservative (income focus)"
        elif risk_tolerance <= 6:
            label = "balanced (growth + income)"
        elif risk_tolerance <= 8:
            label = "moderately aggressive (growth focus)"
        else:
            label = "aggressive (maximum growth)"

        return {
            "risk_tolerance": risk_tolerance,
            "risk_profile": label,
            "volatility_cap": round(volatility_cap, 4),
            "optimal": {
                "name": best[0],
                "allocations": best[1],
                "expected_return": round(best[2], 4),
                "volatility": round(best[3], 4),
                "sharpe_ratio": round(best[4], 4),
            },
            "alternatives": [
                {
                    "name": opt[0],
                    "expected_return": round(opt[2], 4),
                    "volatility": round(opt[3], 4),
                    "sharpe_ratio": round(opt[4], 4),
                }
                for opt in top3[1:]
            ],
            "candidates_evaluated": len(scored),
        }

    @classmethod
    def glide_path(cls, age: int = 30) -> dict:
        """
        Lifecycle (target-date) allocation: equity share declines with age.

        equity = clamp(110 - age, 20%, 90%)
        """
        age = max(0, min(100, int(age)))
        equity_share = max(0.20, min(0.90, (110 - age) / 100.0))
        bond_cash = 1.0 - equity_share

        allocations = {
            "us_stocks": round(equity_share * 0.50, 4),
            "intl_stocks": round(equity_share * 0.30, 4),
            "real_estate": round(equity_share * 0.20, 4),
            "bonds": round(bond_cash * 0.90, 4),
            "cash": round(bond_cash * 0.10, 4),
        }

        expected_return, volatility, sharpe = cls._score(allocations)

        return {
            "age": age,
            "equity_share": round(equity_share, 4),
            "allocations": allocations,
            "expected_return": round(expected_return, 4),
            "volatility": round(volatility, 4),
            "sharpe_ratio": round(sharpe, 4),
        }

    @classmethod
    def efficient_frontier(cls, points: int = 8) -> list[dict]:
        """Sweep equity allocations from 20% to 100% and return the risk/return curve."""
        points = max(2, min(50, int(points)))
        curve = []
        for i in range(points):
            equity_share = 0.20 + i * (0.80 / max(1, points - 1))
            allocations = {
                "us_stocks": round(equity_share * 0.50, 4),
                "intl_stocks": round(equity_share * 0.30, 4),
                "real_estate": round(equity_share * 0.20, 4),
                "bonds": round((1 - equity_share) * 0.90, 4),
                "cash": round((1 - equity_share) * 0.10, 4),
            }
            expected_return, volatility, sharpe = cls._score(allocations)
            curve.append({
                "equity_share": round(equity_share, 4),
                "expected_return": round(expected_return, 4),
                "volatility": round(volatility, 4),
                "sharpe_ratio": round(sharpe, 4),
            })
        return curve

    @staticmethod
    def strategy_for_tolerance(risk_tolerance: int) -> str:
        """Map a risk tolerance 0-10 to the closest named portfolio strategy."""
        risk_tolerance = max(0, min(10, int(risk_tolerance)))
        if risk_tolerance <= 2:
            return "recession_defense"
        elif risk_tolerance <= 4:
            return "dividend_income"
        elif risk_tolerance <= 6:
            return "balanced"
        else:
            return "hyper_growth"
