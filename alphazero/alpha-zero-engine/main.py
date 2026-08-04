"""Alpha Zero Engine — Multiverse Predictor

Usage:
    python main.py                    # Run default simulation
    python main.py --universes 500    # Run 500 parallel universes
    python main.py --strategy hyper_growth
    python main.py --serve            # Start web server
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.character import Gender
from engine.simulation import SimulationOrchestrator, SimulationConfig
from finance.portfolio import PortfolioEngine, STRATEGIES


def run_cli(args):
    """Run simulation from command line."""
    config = SimulationConfig(
        name=args.name,
        age=args.age,
        gender=Gender[args.gender.upper()],
        birthplace=args.birthplace,
        current_city=args.city,
        happiness=args.happiness,
        health=args.health,
        smarts=args.smarts,
        looks=args.looks,
        karma=args.karma,
        starting_money=args.money,
        initial_portfolio=args.portfolio,
        seed=args.seed,
        num_universes=args.universes,
        max_workers=args.workers,
        portfolio_strategy=args.strategy,
    )

    orchestrator = SimulationOrchestrator(config)

    if args.mode == "single":
        print(f"\n{'='*60}")
        print(f"  Alpha Zero — Single Universe Simulation")
        print(f"  Character: {config.name}, Age {config.age}")
        print(f"{'='*60}\n")

        steps = orchestrator.run_single()
        print(f"Simulated {len(steps)} years")

        if steps:
            final = steps[-1]
            print(f"\nFinal State (Age {final.age}):")
            print(f"  Happiness: {final.attributes_after['happiness']}")
            print(f"  Health:    {final.attributes_after['health']}")
            print(f"  Smarts:    {final.attributes_after['smarts']}")
            print(f"  Looks:     {final.attributes_after['looks']}")
            print(f"  Net Worth: ${final.attributes_after['net_worth']:,.2f}")
            print(f"  Events:    {final.attributes_after['event_count']}")

    elif args.mode == "multiverse":
        print(f"\n{'='*60}")
        print(f"  Alpha Zero — Multiverse Simulation")
        print(f"  Character: {config.name}, Age {config.age}")
        print(f"  Universes: {config.num_universes}")
        print(f"{'='*60}\n")

        report = orchestrator.run_multiverse()

        print(f"Simulated {report.total_simulations} universes")
        print(f"\nConvergence Rate: {report.convergence_rate:.1%}")
        print(f"Sharpe Ratio:     {report.sharpe_ratio:.2f}")
        print(f"Beta:             {report.beta:.2f}")
        print(f"Alpha:            ${report.alpha:,.2f}")
        print(f"Avg Years Lived:  {report.avg_years_lived:.1f}")

        print(f"\nBest Net Worth Universe: {report.best_net_worth.universe_id}")
        print(f"  Final Net Worth: ${report.best_net_worth.final_net_worth:,.2f}")

        print(f"\nBest Happiness Universe: {report.best_happiness.universe_id}")
        print(f"  Final Happiness: {report.best_happiness.final_happiness}")

        print(f"\nOutcome Distribution:")
        for outcome, count in report.outcome_distribution.items():
            pct = count / report.total_simulations * 100
            print(f"  {outcome:12s}: {count:4d} ({pct:.1f}%)")

    elif args.mode == "portfolio":
        print(f"\n{'='*60}")
        print(f"  Alpha Zero — Portfolio Comparison")
        print(f"  Initial: ${config.initial_portfolio:,.2f}")
        print(f"{'='*60}\n")

        result = orchestrator.run_with_portfolio(args.strategy)

        print(f"Strategy: {args.strategy}")
        print(f"  Final Portfolio: ${result['final_portfolio_value']:,.2f}")
        print(f"  Final Net Worth: ${result['final_net_worth']:,.2f}")
        print(f"  Total Return:    {result['total_return']:.1f}%")
        print(f"  Years Simulated: {result['steps']}")

        # Compare all strategies
        print(f"\n{'='*60}")
        print(f"  All Strategies Comparison")
        print(f"{'='*60}\n")

        market_returns = [0.10, -0.05, 0.15, 0.08, -0.12, 0.20, 0.05, 0.12, -0.03, 0.18]
        comparison = PortfolioEngine.compare_strategies(
            config.initial_portfolio, 10, market_returns, seed=config.seed
        )

        print(f"{'Strategy':<25} {'Final Value':>15} {'Return':>10} {'Vol':>8}")
        print(f"{'-'*60}")
        for name, data in sorted(comparison.items(), key=lambda x: x[1]["final_value"], reverse=True):
            print(f"{data['name']:<25} ${data['final_value']:>14,.2f} {data['total_return_pct']:>9.1f}% {data['volatility']:>7.1%}")


def serve(args):
    """Start the web server."""
    from api.routes import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)


def main():
    parser = argparse.ArgumentParser(description="Alpha Zero — Multiverse Predictor")
    parser.add_argument("--mode", choices=["single", "multiverse", "portfolio"], default="multiverse")
    parser.add_argument("--name", default="Player")
    parser.add_argument("--age", type=int, default=20)
    parser.add_argument("--gender", default="male")
    parser.add_argument("--birthplace", default="Manila")
    parser.add_argument("--city", default="Manila")
    parser.add_argument("--happiness", type=int, default=50)
    parser.add_argument("--health", type=int, default=70)
    parser.add_argument("--smarts", type=int, default=50)
    parser.add_argument("--looks", type=int, default=50)
    parser.add_argument("--karma", type=int, default=50)
    parser.add_argument("--money", type=float, default=0.0)
    parser.add_argument("--portfolio", type=float, default=100000.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--universes", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--strategy", default="balanced", choices=list(STRATEGIES.keys()))
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--serve", action="store_true", help="Start web server")

    args = parser.parse_args()

    if args.serve:
        serve(args)
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
