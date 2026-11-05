"""Finance metrics — Sharpe ratio, Alpha, Beta, convergence analysis."""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - type hints only, avoids circular import
    from engine.monte_carlo import MultiverseReport


def compute_sharpe_ratio(returns: list[float], risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio: (mean_return - risk_free) / std_dev

    Args:
        returns: List of annual returns
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        Sharpe ratio (higher is better)
    """
    if not returns or len(returns) < 2:
        return 0.0

    mean_return = statistics.mean(returns)
    std_dev = statistics.stdev(returns)

    if std_dev == 0:
        return 0.0

    return (mean_return - risk_free_rate) / std_dev


def compute_alpha(
    portfolio_return: float,
    benchmark_return: float,
    beta: float,
    risk_free_rate: float = 0.02,
) -> float:
    """
    Calculate Jensen's Alpha: excess return over what beta would predict.

    Alpha = portfolio_return - [risk_free + beta * (benchmark_return - risk_free)]
    """
    expected = risk_free_rate + beta * (benchmark_return - risk_free_rate)
    return portfolio_return - expected


def compute_beta(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
) -> float:
    """
    Calculate Beta: portfolio volatility relative to benchmark.

    Beta = Cov(portfolio, benchmark) / Var(benchmark)
    """
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        return 1.0

    p_mean = statistics.mean(portfolio_returns)
    b_mean = statistics.mean(benchmark_returns)

    covariance = sum(
        (p - p_mean) * (b - b_mean)
        for p, b in zip(portfolio_returns, benchmark_returns)
    ) / (len(portfolio_returns) - 1)

    variance = sum((b - b_mean) ** 2 for b in benchmark_returns) / (len(benchmark_returns) - 1)

    if variance == 0:
        return 1.0

    return covariance / variance


def compute_max_drawdown(values: list[float]) -> float:
    """Calculate maximum drawdown from a series of portfolio values."""
    if not values:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for value in values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak
        if drawdown > max_dd:
            max_dd = drawdown

    return max_dd


def compute_convergence(
    universe_values: list[float],
    tolerance_pct: float = 0.20,
) -> float:
    """
    Calculate convergence rate: % of universes within tolerance of mean.

    Args:
        universe_values: Final values from each universe
        tolerance_pct: Tolerance as percentage of mean (default 20%)

    Returns:
        Convergence rate (0.0 to 1.0)
    """
    if not universe_values:
        return 0.0

    mean_val = statistics.mean(universe_values)
    tolerance = mean_val * tolerance_pct

    converged = sum(
        1 for v in universe_values
        if abs(v - mean_val) <= tolerance
    )

    return converged / len(universe_values)


def compute_metrics(report: MultiverseReport) -> dict:
    """Compute all finance metrics from a multiverse report."""
    net_worths = [u.final_net_worth for u in report.parallel_universes]
    returns = [
        (u.final_net_worth - report.anchor_universe.final_net_worth)
        / max(1, report.anchor_universe.final_net_worth)
        for u in report.parallel_universes
    ]

    # Benchmark: anchor universe return
    benchmark_return = 0.0  # Anchor is the baseline

    # Portfolio returns from steps
    portfolio_returns = []
    for universe in report.parallel_universes[:10]:  # Sample first 10
        if universe.steps:
            for step in universe.steps:
                if "portfolio_value" in step.attributes_after:
                    portfolio_returns.append(step.attributes_after.get("portfolio_value", 0))

    metrics = {
        "sharpe_ratio": compute_sharpe_ratio(returns),
        "alpha": compute_alpha(
            statistics.mean(returns) if returns else 0,
            benchmark_return,
            report.beta,
        ),
        "beta": report.beta,
        "convergence_rate": report.convergence_rate,
        "avg_net_worth": statistics.mean(net_worths) if net_worths else 0,
        "median_net_worth": statistics.median(net_worths) if net_worths else 0,
        "std_net_worth": statistics.stdev(net_worths) if len(net_worths) > 1 else 0,
        "max_drawdown": compute_max_drawdown(net_worths),
        "best_universe_id": report.best_net_worth.universe_id,
        "best_net_worth": report.best_net_worth.final_net_worth,
        "best_happiness_universe": report.best_happiness.universe_id,
        "best_happiness": report.best_happiness.final_happiness,
        "avg_years_lived": report.avg_years_lived,
        "outcome_distribution": report.outcome_distribution,
        "total_simulations": report.total_simulations,
    }

    return metrics
