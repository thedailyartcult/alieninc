"""Market simulator — deterministic market data generation with macro events."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class MarketYear:
    """Market conditions for a single year."""

    year: int
    sp500_return: float
    bond_return: float
    inflation: float
    fed_rate: float
    gdp_growth: float
    unemployment: float
    regime: str  # "bull", "bear", "stagnant", "crisis"


class MarketSimulator:
    """
    Deterministic market simulator with macroeconomic regimes.

    Generates realistic market returns based on:
    - Historical base rates
    - Macroeconomic regime cycles
    - Random shocks (deterministic per seed)
    """

    # Historical base annual returns
    BASE_SP500_RETURN = 0.10
    BASE_BOND_RETURN = 0.04
    BASE_INFLATION = 0.025
    BASE_FED_RATE = 0.03
    BASE_GDP_GROWTH = 0.025
    BASE_UNEMPLOYMENT = 0.05

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._cache: dict[int, MarketYear] = {}

    def _determine_regime(self, year: int) -> str:
        """Determine the macroeconomic regime for a given year."""
        # Regime cycle: ~10 year bull, ~2 year bear, ~3 year stagnant
        cycle_pos = (year - 2026) % 15

        # Random regime shifts
        shock = self.rng.random()

        if shock < 0.05:
            return "crisis"
        elif cycle_pos < 8:
            return "bull"
        elif cycle_pos < 10:
            return "bear"
        else:
            return "stagnant"

    def _generate_year(self, year: int) -> MarketYear:
        """Generate market conditions for a specific year."""
        regime = self._determine_regime(year)

        # Regime modifiers
        regime_params = {
            "bull": {
                "sp500_mult": 1.5, "bond_mult": 0.8, "inflation_adj": -0.005,
                "fed_adj": 0.005, "gdp_mult": 1.3, "unemployment_adj": -0.01,
            },
            "bear": {
                "sp500_mult": -0.5, "bond_mult": 1.3, "inflation_adj": 0.01,
                "fed_adj": -0.01, "gdp_mult": 0.5, "unemployment_adj": 0.02,
            },
            "stagnant": {
                "sp500_mult": 0.3, "bond_mult": 1.0, "inflation_adj": 0.0,
                "fed_adj": 0.0, "gdp_mult": 0.7, "unemployment_adj": 0.005,
            },
            "crisis": {
                "sp500_mult": -1.5, "bond_mult": 1.5, "inflation_adj": 0.02,
                "fed_adj": -0.02, "gdp_mult": -0.5, "unemployment_adj": 0.04,
            },
        }

        params = regime_params[regime]

        # Generate with noise
        sp500_return = (
            self.BASE_SP500_RETURN * params["sp500_mult"]
            + self.rng.gauss(0, 0.15)
        )
        bond_return = (
            self.BASE_BOND_RETURN * params["bond_mult"]
            + self.rng.gauss(0, 0.05)
        )
        inflation = max(0, self.BASE_INFLATION + params["inflation_adj"] + self.rng.gauss(0, 0.01))
        fed_rate = max(0, self.BASE_FED_RATE + params["fed_adj"] + self.rng.gauss(0, 0.005))
        gdp_growth = self.BASE_GDP_GROWTH * params["gdp_mult"] + self.rng.gauss(0, 0.01)
        unemployment = max(0.02, min(0.15, self.BASE_UNEMPLOYMENT + params["unemployment_adj"] + self.rng.gauss(0, 0.005)))

        return MarketYear(
            year=year,
            sp500_return=round(sp500_return, 4),
            bond_return=round(bond_return, 4),
            inflation=round(inflation, 4),
            fed_rate=round(fed_rate, 4),
            gdp_growth=round(gdp_growth, 4),
            unemployment=round(unemployment, 4),
            regime=regime,
        )

    def get_year(self, year: int) -> MarketYear:
        """Get market conditions for a year (cached)."""
        if year not in self._cache:
            self._cache[year] = self._generate_year(year)
        return self._cache[year]

    def get_year_return(self, year: int) -> float:
        """Get the base market return for a year (used by portfolio engine)."""
        market = self.get_year(year)
        return market.sp500_return

    def generate_series(self, start_year: int, end_year: int) -> list[MarketYear]:
        """Generate market data for a range of years."""
        return [self.get_year(y) for y in range(start_year, end_year + 1)]

    def get_scenario(self, scenario: str, years: int) -> list[MarketYear]:
        """
        Generate a specific scenario for multiverse comparison.

        Scenarios: "hyper_growth", "recession", "stagnant"
        """
        original_rng = self.rng.getstate()

        scenario_params = {
            "hyper_growth": {"sp500_boost": 0.08, "inflation_adj": -0.01},
            "recession": {"sp500_boost": -0.12, "inflation_adj": 0.02},
            "stagnant": {"sp500_boost": -0.05, "inflation_adj": 0.0},
        }

        params = scenario_params.get(scenario, scenario_params["stagnant"])
        results = []

        for i in range(years):
            year = 2026 + i
            market = self.get_year(year)

            # Apply scenario modifiers
            market.sp500_return += params["sp500_boost"]
            market.inflation += params["inflation_adj"]
            market.regime = scenario

            results.append(market)

        self.rng.setstate(original_rng)
        return results
