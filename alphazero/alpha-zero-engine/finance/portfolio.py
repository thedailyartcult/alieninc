"""Portfolio engine — allocation strategies and annual rebalancing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine.character import Character


# Predefined portfolio strategies
STRATEGIES = {
    "hyper_growth": {
        "name": "Hyper-Growth",
        "allocations": {
            "tech_stocks": 0.40,
            "leveraged_etf": 0.25,
            "crypto": 0.15,
            "emerging_markets": 0.10,
            "cash": 0.10,
        },
        "expected_return": 0.18,
        "volatility": 0.35,
        "sharpe_target": 2.1,
    },
    "balanced": {
        "name": "Balanced",
        "allocations": {
            "us_stocks": 0.30,
            "intl_stocks": 0.20,
            "bonds": 0.25,
            "real_estate": 0.15,
            "cash": 0.10,
        },
        "expected_return": 0.08,
        "volatility": 0.12,
        "sharpe_target": 1.0,
    },
    "recession_defense": {
        "name": "Recession Defense",
        "allocations": {
            "consumer_staples": 0.30,
            "gold": 0.25,
            "bonds": 0.25,
            "utilities": 0.10,
            "cash": 0.10,
        },
        "expected_return": 0.05,
        "volatility": 0.08,
        "sharpe_target": 1.4,
    },
    "dividend_income": {
        "name": "Dividend Aristocrats",
        "allocations": {
            "dividend_stocks": 0.40,
            "reits": 0.20,
            "bonds": 0.25,
            "preferred_stock": 0.10,
            "cash": 0.05,
        },
        "expected_return": 0.06,
        "volatility": 0.10,
        "sharpe_target": 0.8,
    },
}


class PortfolioEngine:
    """Manages portfolio allocations and rebalancing."""

    @staticmethod
    def get_default_allocation(strategy: str) -> dict:
        """Get the allocation dictionary for a strategy."""
        strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
        return dict(strat["allocations"])

    @staticmethod
    def get_strategy_info(strategy: str) -> dict:
        """Get full strategy info."""
        return dict(STRATEGIES.get(strategy, STRATEGIES["balanced"]))

    @staticmethod
    def apply_annual_return(character: Character, market_return: float, strategy: str) -> float:
        """
        Apply annual market return to the character's portfolio.

        Args:
            character: The character with portfolio
            market_return: Base market return for this year (-1.0 to +2.0)
            strategy: Portfolio strategy name

        Returns:
            Actual portfolio return
        """
        strat = STRATEGIES.get(strategy, STRATEGIES["balanced"])
        allocations = strat["allocations"]
        base_expected = strat["expected_return"]
        volatility = strat["volatility"]

        # Calculate asset-class weighted return
        portfolio_return = 0.0
        for asset_class, weight in allocations.items():
            # Each asset class has different sensitivity to market
            sensitivity = {
                "tech_stocks": 1.5,
                "leveraged_etf": 2.0,
                "crypto": 2.5,
                "emerging_markets": 1.3,
                "us_stocks": 1.0,
                "intl_stocks": 0.9,
                "bonds": 0.3,
                "real_estate": 0.7,
                "consumer_staples": 0.6,
                "gold": 0.2,
                "utilities": 0.5,
                "dividend_stocks": 0.8,
                "reits": 0.7,
                "preferred_stock": 0.4,
                "cash": 0.02,
            }.get(asset_class, 1.0)

            asset_return = market_return * sensitivity
            portfolio_return += weight * asset_return

        # Add strategy-specific alpha
        alpha = character.rng.gauss(0, volatility * 0.3)
        portfolio_return += alpha

        # Apply to portfolio
        old_value = character.portfolio_value
        character.portfolio_value *= (1 + portfolio_return)
        character.portfolio_value = max(0, character.portfolio_value)
        character._recalc_net_worth()

        return portfolio_return

    @staticmethod
    def rebalance(character: Character, strategy: str) -> dict:
        """Rebalance portfolio to target allocations."""
        allocations = PortfolioEngine.get_default_allocation(strategy)
        total = character.portfolio_value

        new_allocations = {}
        for asset, weight in allocations.items():
            new_allocations[asset] = total * weight

        character.portfolio_allocations = new_allocations
        return new_allocations

    @staticmethod
    def compare_strategies(
        initial_value: float,
        years: int,
        market_returns: list[float],
        seed: int = 42,
    ) -> dict:
        """Compare all strategies over the same market conditions."""
        import random
        rng = random.Random(seed)

        results = {}
        for strategy_name, strategy in STRATEGIES.items():
            value = initial_value
            annual_returns = []

            for year_return in market_returns[:years]:
                # Simulate portfolio return
                portfolio_return = 0.0
                for asset_class, weight in strategy["allocations"].items():
                    sensitivity = {
                        "tech_stocks": 1.5, "leveraged_etf": 2.0, "crypto": 2.5,
                        "emerging_markets": 1.3, "us_stocks": 1.0, "intl_stocks": 0.9,
                        "bonds": 0.3, "real_estate": 0.7, "consumer_staples": 0.6,
                        "gold": 0.2, "utilities": 0.5, "dividend_stocks": 0.8,
                        "reits": 0.7, "preferred_stock": 0.4, "cash": 0.02,
                    }.get(asset_class, 1.0)
                    portfolio_return += weight * year_return * sensitivity

                portfolio_return += rng.gauss(0, strategy["volatility"] * 0.3)
                value *= (1 + portfolio_return)
                annual_returns.append(portfolio_return)

            total_return = (value / initial_value - 1) * 100
            avg_return = sum(annual_returns) / len(annual_returns) if annual_returns else 0

            results[strategy_name] = {
                "name": strategy["name"],
                "final_value": value,
                "total_return_pct": round(total_return, 2),
                "annualized_return_pct": round(avg_return * 100, 2),
                "volatility": strategy["volatility"],
                "sharpe_target": strategy["sharpe_target"],
            }

        return results
