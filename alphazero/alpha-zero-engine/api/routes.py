"""API Routes — Flask backend for Alpha Zero web interface."""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, stream_with_context

from engine.character import Gender
from engine.simulation import SimulationOrchestrator, SimulationConfig
from engine.monte_carlo import MonteCarloEngine
from engine.fsm import FSM
from finance.portfolio import PortfolioEngine, STRATEGIES
from finance.market import MarketSimulator
from finance.metrics import compute_metrics
from infra import analytics
from infra.cache import healthy as redis_healthy

# The AI agents live in the repo-root ai/ package (sibling of alpha-zero-engine).
_AI_DIR = str(Path(__file__).resolve().parents[2])
if _AI_DIR not in sys.path:
    sys.path.insert(0, _AI_DIR)

OLLAMA_DISABLE = os.environ.get("OLLAMA_DISABLE", "0") == "1"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
ALPHACORE_BIN = Path(__file__).resolve().parents[1] / "core" / "bin" / "alphacore"
_PID = os.getpid()


def _rss_mb() -> float:
    """Resident set size of this process in MB (Linux /proc)."""
    try:
        with open(f"/proc/{_PID}/statm") as f:
            pages = int(f.read().split()[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / (1024 * 1024), 2)
    except (OSError, ValueError, IndexError):
        return 0.0


def _ollama_up() -> bool:
    if OLLAMA_DISABLE:
        return False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def create_app():
    app = Flask(__name__, template_folder="../web/templates", static_folder="../web/static")
    app.secret_key = os.urandom(24)

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    # ------------------------------------------------------------------
    # Monitoring & analytics hooks
    # ------------------------------------------------------------------

    @app.before_request
    def _az_start_timer():
        request.environ["_az_start"] = time.perf_counter()

    @app.after_request
    def _az_record_request(response):
        start = request.environ.pop("_az_start", None)
        duration = (time.perf_counter() - start) * 1000 if start else 0.0
        endpoint = request.path
        # Skip the health/analytics endpoints themselves to avoid recursion.
        if endpoint != "/api/health" and not endpoint.startswith("/api/analytics"):
            analytics.record_request(
                request.method, endpoint, response.status_code, round(duration, 2)
            )
        return response

    # ------------------------------------------------------------------
    # Monitoring & analytics endpoints
    # ------------------------------------------------------------------

    @app.route("/api/health")
    def api_health():
        """Liveness + dependency status for the deployed app."""
        usage = analytics.usage_summary()
        return jsonify({
            "status": "ok",
            "uptime_seconds": round(time.time() - analytics._started_at, 2),
            "process": {
                "pid": _PID,
                "memory_rss_mb": _rss_mb(),
                "started_at": analytics._started_at,
            },
            "requests": {
                "total": usage["total_requests"],
                "errors": usage["error_count"],
            },
            "dependencies": {
                "ollama": _ollama_up(),
                "ollama_disabled": OLLAMA_DISABLE,
                "redis": redis_healthy(),
                "alphacore_binary": ALPHACORE_BIN.exists(),
            },
        })

    @app.route("/api/analytics/summary")
    def api_analytics_summary():
        return jsonify(analytics.summary())

    @app.route("/api/analytics/requests")
    def api_analytics_requests():
        limit = request.args.get("limit", 100, type=int)
        return jsonify({"requests": analytics.request_history(limit)})

    @app.route("/api/analytics/runs")
    def api_analytics_runs():
        limit = request.args.get("limit", 50, type=int)
        return jsonify({"runs": analytics.run_history(limit)})

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

        analytics.record_simulation("single", {
            "name": config.name,
            "age": config.age,
            "strategy": config.portfolio_strategy,
            "years": len(steps),
        })

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

        analytics.record_simulation("multiverse", {
            "name": config.name,
            "universes": report.total_simulations,
            "strategy": config.portfolio_strategy,
            "convergence_rate": report.convergence_rate,
            "sharpe_ratio": report.sharpe_ratio,
            "avg_years_lived": report.avg_years_lived,
        })

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

        analytics.record_simulation("branch", {
            "name": config.name,
            "branch_age": data.get("branch_age"),
            "universes": report.total_simulations,
            "convergence_rate": report.convergence_rate,
        })

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

    # ------------------------------------------------------------------
    # AI Agent routes
    # ------------------------------------------------------------------

    @app.route("/api/ai/interview", methods=["POST"])
    def api_ai_interview():
        """Conduct an AI interview and build a Character profile."""
        from ai.interview_agent import InterviewAgent

        data = request.json or {}
        text = data.get("interview_text") or data.get("initial_interview_text") or ""
        if not text:
            fields = [f"{k}: {v}" for k, v in data.items()
                      if k in ("name", "age", "gender", "occupation") and v not in (None, "")]
            text = ", ".join(fields)

        agent = InterviewAgent()
        if OLLAMA_DISABLE:
            persona = agent._extract_with_regex(text)
        else:
            persona = agent.extract_persona_from_text(text)

        for field in ("name", "age", "gender", "occupation", "birthplace", "current_city"):
            explicit = data.get(field)
            if explicit not in (None, ""):
                persona[field] = explicit
        agent.current_profile = persona

        return jsonify({
            "persona": persona,
            "profile": persona,
            "social_variables": persona.get("social_variables", {}),
            "status": "success",
        })

    @app.route("/api/ai/coach", methods=["POST"])
    def api_ai_coach():
        """Provide life coaching advice for a Character profile."""
        from ai.life_coach import LifeCoachAgent

        data = request.json or {}
        character_data = data.get("character_json") or data.get("character") or {}
        if isinstance(character_data, str):
            try:
                character_data = json.loads(character_data)
            except (json.JSONDecodeError, TypeError):
                character_data = {}

        situation = data.get("situation", "general")
        agent = LifeCoachAgent()
        advice = agent.provide_advice(character_data, situation)
        return jsonify({"status": "success", "result": advice})

    @app.route("/api/ai/analyze", methods=["POST"])
    def api_ai_analyze():
        """Analyze simulation outcomes and suggest life paths."""
        from ai.decision_assistant import DecisionAssistantAgent

        data = request.json or {}
        results = data.get("simulation_results", [])
        agent = DecisionAssistantAgent()
        analysis = agent.analyze_simulation_outcomes(results)
        return jsonify({"status": "success", "result": analysis})

    @app.route("/api/ai/narrate", methods=["POST"])
    def api_ai_narrate():
        """Generate a narrative from a simulation result."""
        from ai.storyteller import StorytellerAgent
        from engine.character import Character, Gender

        data = request.json or {}
        agent = StorytellerAgent()

        simulation_results = data.get("simulation_results")
        if simulation_results:
            result = agent.generate_simulation_narrative(simulation_results)
        else:
            sim = data.get("simulation_result") or {}
            if isinstance(sim, str):
                try:
                    sim = json.loads(sim)
                except (json.JSONDecodeError, TypeError):
                    sim = {}
            character = Character(
                name=data.get("character_name", sim.get("character_name", "Unknown")),
                age=int(sim.get("final_age", sim.get("age", 30))),
                gender=Gender.MALE,
                happiness=int(sim.get("final_happiness", sim.get("happiness", 50))),
                health=int(sim.get("final_health", sim.get("health", 70))),
                net_worth=float(sim.get("final_net_worth", sim.get("net_worth", 0.0))),
                occupation=sim.get("occupation", "Unknown"),
            )
            result = {
                "character_name": character.name,
                "narrative": agent.generate_character_narrative(character, sim),
            }

        return jsonify({"status": "success", "result": result})

    @app.route("/api/ai/financial_advisor", methods=["POST"])
    def api_ai_financial_advisor():
        """Financial advice: budget, debt, savings, and allocation guidance."""
        from ai.financial_advisor import FinancialAdvisorAgent

        data = request.json or {}
        character_data = data.get("character_json") or data.get("character") or {}
        if isinstance(character_data, str):
            try:
                character_data = json.loads(character_data)
            except (json.JSONDecodeError, TypeError):
                character_data = {}

        situation = data.get("situation", "general")
        agent = FinancialAdvisorAgent()
        advice = agent.provide_advice(character_data, situation)
        return jsonify({"status": "success", "result": advice})

    @app.route("/api/ai/health_coach", methods=["POST"])
    def api_ai_health_coach():
        """Health coaching: wellness assessment, exercise, sleep, stress."""
        from ai.health_coach import HealthCoachAgent

        data = request.json or {}
        character_data = data.get("character_json") or data.get("character") or {}
        if isinstance(character_data, str):
            try:
                character_data = json.loads(character_data)
            except (json.JSONDecodeError, TypeError):
                character_data = {}

        situation = data.get("situation", "general")
        agent = HealthCoachAgent()
        advice = agent.provide_advice(character_data, situation)
        return jsonify({"status": "success", "result": advice})

    @app.route("/api/ai/mentor", methods=["POST"])
    def api_ai_mentor():
        """Mentoring session synthesizing financial, health, and life coaching."""
        from ai.mentor import MentorAgent

        data = request.json or {}
        character_data = data.get("character_json") or data.get("character") or {}
        if isinstance(character_data, str):
            try:
                character_data = json.loads(character_data)
            except (json.JSONDecodeError, TypeError):
                character_data = {}

        question = data.get("question", "") or ""
        agent = MentorAgent()
        result = agent.provide_mentorship(character_data, question)
        return jsonify({"status": "success", "result": result})

    @app.route("/api/ai/advisors", methods=["POST"])
    def api_ai_advisors():
        """Advisor Panel: interview -> multiverse -> financial / health / mentor
        specialists for one character, with a durable per-character dossier."""
        from ai.advisor_panel import run_advisor_panel

        data = request.json or {}
        text = data.get("interview_text") or data.get("initial_interview_text") or ""
        if not text:
            fields = [f"{k}: {v}" for k, v in data.items()
                      if k in ("name", "age", "gender", "occupation") and v not in (None, "")]
            text = ", ".join(fields)

        max_universes = int(data.get("max_universes", 100))
        result = run_advisor_panel(
            text,
            workspace=data.get("workspace", "web"),
            overrides=data,
            persist_memory=data.get("persist_memory", True),
            max_universes=max_universes,
        )
        return jsonify(result)

    @app.route("/api/ai/advisor_dossier", methods=["POST"])
    def api_ai_advisor_dossier():
        """Recall a character's durable advisor dossier (cross-session continuity)."""
        from ai.advisor_dossier import recall_advisor_dossier

        data = request.json or {}
        character_name = data.get("character_name") or data.get("name") or ""
        workspace = data.get("workspace", "web")
        limit = int(data.get("limit", 10))
        dossiers = recall_advisor_dossier(character_name, workspace=workspace, limit=limit)
        return jsonify({
            "status": "success",
            "character_name": character_name,
            "result": {"count": len(dossiers), "dossiers": dossiers},
        })

    @app.route("/api/ai/memory", methods=["POST"])
    def api_ai_memory():
        """Store / retrieve cross-session learnings via the memory agent."""
        from ai.memory_system import MemorySystemAgent

        data = request.json or {}
        operation = data.get("operation", "store")
        payload = data.get("data", {})
        query = data.get("query")
        session_id = data.get("session_id")
        workspace = data.get("workspace", "alphazero")

        agent = MemorySystemAgent(workspace=workspace)
        result = {"error": f"Unknown operation: {operation}"}

        if operation == "store":
            learning_id = agent.store_learning(payload, session_id=session_id)
            result = {"learning_id": learning_id, "stored": True}
        elif operation == "retrieve":
            learnings = agent.retrieve_learnings(query=query)
            result = {"results": learnings, "count": len(learnings)}
        elif operation == "update":
            learning_id = payload.get("learning_id")
            updated = agent.update_learning(learning_id, payload.get("updates", {})) if learning_id else False
            result = {"updated": updated}
        elif operation == "delete":
            learning_id = payload.get("learning_id")
            deleted = agent.delete_learning(learning_id) if learning_id else False
            result = {"deleted": deleted}
        elif operation == "create_session":
            session_id = session_id or payload.get("session_id", "default")
            created = agent.create_session(session_id, payload.get("context", {}))
            result = {"session_id": session_id, "created": created}
        elif operation == "end_session":
            session_id = session_id or payload.get("session_id", "default")
            ended = agent.end_session(session_id, payload.get("insights"))
            result = {"session_id": session_id, "ended": ended}

        return jsonify({"status": "success", "result": result})

    @app.route("/api/ai/pipeline", methods=["POST"])
    def api_ai_pipeline():
        """Run the end-to-end AI pipeline: interview -> simulate -> analyze
        -> coach -> narrate -> memory."""
        from ai.pipeline import run_ai_pipeline

        data = request.json or {}
        text = data.get("interview_text") or data.get("initial_interview_text") or ""
        if not text:
            fields = [f"{k}: {v}" for k, v in data.items()
                      if k in ("name", "age", "gender", "occupation") and v not in (None, "")]
            text = ", ".join(fields)

        max_universes = int(data.get("max_universes", 100))
        result = run_ai_pipeline(
            text,
            workspace=data.get("workspace", "web"),
            overrides=data,
            persist_memory=data.get("persist_memory", True),
            max_universes=max_universes,
        )
        return jsonify(result)

    return app
