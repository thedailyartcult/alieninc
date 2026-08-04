"""API Routes — Flask backend for Alpha Zero web interface."""

import json
import os
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

from engine.character import Gender
from engine.simulation import SimulationOrchestrator, SimulationConfig
from engine.monte_carlo import MonteCarloEngine
from engine.fsm import FSM
from finance.portfolio import PortfolioEngine, STRATEGIES
from finance.market import MarketSimulator
from finance.metrics import compute_metrics


def create_app():
    app = Flask(__name__, template_folder="../web/templates", static_folder="../web/static")
    app.secret_key = os.urandom(24)

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/api/simulate", methods=["POST"])
    def api_simulate():
        """Run a single universe simulation."""
        data = request.json

        config = SimulationConfig(
            name=data.get("name", "Player"),
            age=data.get("age", 20),
            gender=Gender(data.get("gender", "male")),
            birthplace=data.get("birthplace", "Manila"),
            current_city=data.get("city", "Manila"),
            happiness=data.get("happiness", 50),
            health=data.get("health", 70),
            smarts=data.get("smarts", 50),
            looks=data.get("looks", 50),
            karma=data.get("karma", 50),
            starting_money=data.get("money", 0),
            initial_portfolio=data.get("portfolio", 0),
            seed=data.get("seed", 42),
            portfolio_strategy=data.get("strategy", "balanced"),
        )

        orchestrator = SimulationOrchestrator(config)
        steps = orchestrator.run_single()

        # Format steps for frontend
        timeline = []
        for step in steps:
            entry = {
                "age": step.age,
                "year": step.year,
                "life_stage": step.life_stage,
                "events": step.events,
                "is_alive": step.is_alive,
            }
            entry.update(step.attributes_after)
            timeline.append(entry)

        return jsonify({
            "character": orchestrator.create_character().to_dict(),
            "timeline": timeline,
            "total_years": len(steps),
        })

    @app.route("/api/multiverse", methods=["POST"])
    def api_multiverse():
        """Run parallel universe simulation."""
        data = request.json

        config = SimulationConfig(
            name=data.get("name", "Player"),
            age=data.get("age", 20),
            gender=Gender(data.get("gender", "male")),
            birthplace=data.get("birthplace", "Manila"),
            current_city=data.get("city", "Manila"),
            happiness=data.get("happiness", 50),
            health=data.get("health", 70),
            smarts=data.get("smarts", 50),
            looks=data.get("looks", 50),
            karma=data.get("karma", 50),
            starting_money=data.get("money", 0),
            initial_portfolio=data.get("portfolio", 100000),
            seed=data.get("seed", 42),
            num_universes=data.get("universes", 100),
            max_workers=data.get("workers", 4),
            portfolio_strategy=data.get("strategy", "balanced"),
        )

        orchestrator = SimulationOrchestrator(config)
        report = orchestrator.run_multiverse()

        # Compute metrics
        metrics = compute_metrics(report)

        # Format for frontend
        result = {
            "total_simulations": report.total_simulations,
            "convergence_rate": report.convergence_rate,
            "sharpe_ratio": report.sharpe_ratio,
            "alpha": report.alpha,
            "beta": report.beta,
            "avg_years_lived": report.avg_years_lived,
            "best_net_worth": {
                "universe_id": report.best_net_worth.universe_id,
                "final_net_worth": report.best_net_worth.final_net_worth,
                "final_happiness": report.best_net_worth.final_happiness,
            },
            "best_happiness": {
                "universe_id": report.best_happiness.universe_id,
                "final_net_worth": report.best_happiness.final_net_worth,
                "final_happiness": report.best_happiness.final_happiness,
            },
            "outcome_distribution": report.outcome_distribution,
            "metrics": metrics,
            "anchor_final": report.anchor_universe.final_state,
        }

        return jsonify(result)

    @app.route("/api/branch", methods=["POST"])
    def api_branch():
        """Branch from a specific point with modifications."""
        data = request.json

        config = SimulationConfig(
            name=data.get("name", "Player"),
            age=data.get("age", 20),
            gender=Gender(data.get("gender", "male")),
            seed=data.get("seed", 42),
            num_universes=data.get("branches", 50),
        )

        orchestrator = SimulationOrchestrator(config)
        character = orchestrator.create_character()
        relations = orchestrator.create_default_relations(character)

        monte_carlo = MonteCarloEngine()
        report = monte_carlo.branch_from_point(
            character, relations,
            branch_age=data.get("branch_age", 25),
            modification=data.get("modification", {}),
            num_branches=data.get("branches", 50),
        )

        metrics = compute_metrics(report)

        return jsonify({
            "branch_age": data.get("branch_age"),
            "modification": data.get("modification"),
            "total_branches": report.total_simulations,
            "convergence_rate": report.convergence_rate,
            "best_branch": {
                "universe_id": report.best_net_worth.universe_id,
                "final_net_worth": report.best_net_worth.final_net_worth,
            },
            "metrics": metrics,
        })

    @app.route("/api/portfolio/compare", methods=["POST"])
    def api_portfolio_compare():
        """Compare all portfolio strategies."""
        data = request.json

        initial_value = data.get("initial_value", 100000)
        years = data.get("years", 10)
        seed = data.get("seed", 42)

        # Generate market returns
        market_sim = MarketSimulator(seed=seed)
        market_returns = [market_sim.get_year_return(2026 + i) for i in range(years)]

        comparison = PortfolioEngine.compare_strategies(
            initial_value, years, market_returns, seed=seed
        )

        return jsonify({
            "strategies": comparison,
            "market_returns": market_returns,
            "initial_value": initial_value,
            "years": years,
        })

    @app.route("/api/portfolio/strategies", methods=["GET"])
    def api_strategies():
        """List all available portfolio strategies."""
        return jsonify({
            "strategies": {
                name: {
                    "name": info["name"],
                    "allocations": info["allocations"],
                    "expected_return": info["expected_return"],
                    "volatility": info["volatility"],
                    "sharpe_target": info["sharpe_target"],
                }
                for name, info in STRATEGIES.items()
            }
        })

    @app.route("/api/market/scenarios", methods=["POST"])
    def api_market_scenarios():
        """Generate market scenarios for multiverse comparison."""
        data = request.json
        years = data.get("years", 10)
        seed = data.get("seed", 42)

        market_sim = MarketSimulator(seed=seed)

        scenarios = {}
        for scenario in ["hyper_growth", "recession", "stagnant"]:
            market_data = market_sim.get_scenario(scenario, years)
            scenarios[scenario] = [
                {
                    "year": m.year,
                    "sp500_return": m.sp500_return,
                    "bond_return": m.bond_return,
                    "inflation": m.inflation,
                    "fed_rate": m.fed_rate,
                    "regime": m.regime,
                }
                for m in market_data
            ]

        return jsonify({"scenarios": scenarios})

    return app
