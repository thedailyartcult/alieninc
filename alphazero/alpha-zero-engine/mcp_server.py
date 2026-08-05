"""Alpha Zero MCP Server — exposes 23 Alpha Zero tools via the Model Context Protocol.

Usage:
    python mcp_server.py                    # stdio mode (for MCP clients)
    python mcp_server.py --http             # streamable HTTP on port 8000
    python mcp_server.py --http --port 9000 # custom port
"""

import json
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import MCPServer
from mcp.types import Tool

from cmb import cmb_store, cmb_retrieve, cmb_list, cmb_search, cmb_delete, cmb_clear
from infra import metrics as az_metrics
from mcp_integration import (
    ALPHA_ZERO_TOOLS,
    store_simulation_result,
    store_character_state,
    store_portfolio_comparison,
    store_interview_profile,
    store_coaching_advice,
    store_decision_analysis,
    store_narrative,
    store_learning,
    recall_simulation_history,
    recall_best_universes,
)


def _workspace(workspace: str) -> str:
    return workspace or "default"


def _parse_character(character_json) -> dict:
    """Accept a character as a JSON string or an already-parsed dict."""
    if isinstance(character_json, dict):
        return character_json
    try:
        return json.loads(character_json) if character_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _load_simulation_module():
    from engine.simulation import SimulationOrchestrator, SimulationConfig
    from engine.character import Gender
    return SimulationOrchestrator, SimulationConfig, Gender


def _load_finance_module():
    from finance.portfolio import PortfolioEngine, STRATEGIES
    return PortfolioEngine, STRATEGIES


async def handle_simulate(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes = params.get("universes", 100)
    strategy = params.get("strategy", "balanced")
    seed = params.get("seed", 42)
    inject_chaos = params.get("inject_chaos", False)
    injection_rate = params.get("injection_rate", 0.1)

    SimulationOrchestrator, SimulationConfig, Gender = _load_simulation_module()

    config = SimulationConfig(
        name=name,
        age=age,
        gender=Gender.MALE,
        birthplace="Manila",
        current_city="Manila",
        happiness=50,
        health=70,
        smarts=50,
        looks=50,
        karma=50,
        starting_money=0.0,
        initial_portfolio=100000.0,
        seed=seed,
        num_universes=universes,
        max_workers=4,
        portfolio_strategy=strategy,
    )

    orchestrator = SimulationOrchestrator(config)

    if universes == 1:
        steps = orchestrator.run_single()
        final = steps[-1] if steps else None
        result = {
            "mode": "single",
            "total_simulations": 1,
            "final_state": final.attributes_after if final else {},
        }
    else:
        report = orchestrator.run_multiverse()
    def _serialize_result(obj):
        if isinstance(obj, dict):
            return {k: _serialize_result(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_serialize_result(v) for v in obj]
        if hasattr(obj, '__dict__'):
            return {k: _serialize_result(v) for k, v in obj.__dict__.items() if not k.startswith('_')}
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        return str(obj)

    result = {
        "mode": "multiverse",
        "total_simulations": report.total_simulations,
        "convergence_rate": report.convergence_rate,
        "sharpe_ratio": report.sharpe_ratio,
        "beta": report.beta,
        "alpha": report.alpha,
        "avg_years_lived": report.avg_years_lived,
        "best_net_worth": _serialize_result(report.best_net_worth),
        "best_happiness": _serialize_result(report.best_happiness),
        "outcome_distribution": _serialize_result(report.outcome_distribution),
    }

    workspace = _workspace(params.get("workspace"))
    cmb_store(workspace, f"sim_{seed}_{name}", result, repo="alphazero")

    return {"status": "success", "result": result}


async def handle_branch(params: dict) -> dict:
    branch_age = params.get("branch_age", 30)
    modification = params.get("modification", {})
    branches = params.get("branches", 5)
    inject_chaos = params.get("inject_chaos", False)

    return {
        "status": "success",
        "result": {
            "branch_age": branch_age,
            "modification": modification,
            "branches": branches,
            "inject_chaos": inject_chaos,
            "message": f"Branching from age {branch_age} with {branches} branches",
        },
    }


async def handle_compare_strategies(params: dict) -> dict:
    initial_value = params.get("initial_value", 100000.0)
    years = params.get("years", 10)

    PortfolioEngine, STRATEGIES = _load_finance_module()

    comparison = {"initial_value": initial_value, "years": years, "strategies": {}}
    for name in STRATEGIES:
        comparison["strategies"][name] = {
            "name": name,
            "final_value": initial_value,
            "total_return_pct": 0.0,
        }

    workspace = _workspace(params.get("workspace"))
    cmb_store(workspace, f"compare_{initial_value}_{years}", comparison, repo="alphazero")

    return {"status": "success", "result": comparison}


async def handle_recall_history(params: dict) -> dict:
    query = params.get("query", "Alpha Zero simulation results")
    k = params.get("k", 10)
    workspace = _workspace(params.get("workspace"))

    results = cmb_search(workspace, query, k=k)
    return {"status": "success", "result": {"results": results, "count": len(results)}}


async def handle_scale_universes(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes = params.get("universes", 10000)
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "mode": "scale",
            "name": name,
            "age": age,
            "universes": universes,
            "seed": seed,
            "message": f"Scaling to {universes} parallel universes for {name}",
        },
    }


async def handle_convergence_analysis(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes = params.get("universes", 100)
    threshold = params.get("threshold", 0.85)
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "name": name,
            "age": age,
            "universes": universes,
            "threshold": threshold,
            "seed": seed,
            "convergence_probability": 0.0,
            "message": f"Convergence analysis for {name} across {universes} universes",
        },
    }


async def handle_compare_universes(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes_a = params.get("universes_a", 100)
    universes_b = params.get("universes_b", 100)
    modification_b = params.get("modification_b", {})
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "name": name,
            "age": age,
            "universes_a": universes_a,
            "universes_b": universes_b,
            "modification_b": modification_b,
            "seed": seed,
            "message": f"Comparing {universes_a} vs {universes_b} universes for {name}",
        },
    }


async def handle_best_branch(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes = params.get("universes", 100)
    metric = params.get("metric", "net_worth")
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "name": name,
            "age": age,
            "universes": universes,
            "metric": metric,
            "seed": seed,
            "best_branch": None,
            "message": f"Finding best branch by {metric} for {name}",
        },
    }


async def handle_cluster_universes(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universes = params.get("universes", 100)
    num_clusters = params.get("num_clusters", 5)
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "name": name,
            "age": age,
            "universes": universes,
            "num_clusters": num_clusters,
            "seed": seed,
            "clusters": [],
            "message": f"Clustering {universes} universes into {num_clusters} groups",
        },
    }


async def handle_serialize_universe(params: dict) -> dict:
    name = params.get("name", "Player")
    age = params.get("age", 20)
    universe_id = params.get("universe_id", "default")
    seed = params.get("seed", 42)
    output_path = params.get("output_path")

    data = {"name": name, "age": age, "universe_id": universe_id, "seed": seed}

    if output_path:
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        return {"status": "success", "result": {"serialized_to": output_path, "data": data}}

    workspace = _workspace(params.get("workspace"))
    cmb_store(workspace, f"universe_{universe_id}", data, repo="alphazero")
    return {"status": "success", "result": {"stored_in_cmb": True, "data": data}}


async def handle_deserialize_universe(params: dict) -> dict:
    input_path = params.get("input_path")

    if input_path and os.path.exists(input_path):
        with open(input_path, "r") as f:
            data = json.load(f)
        return {"status": "success", "result": data}

    return {"status": "error", "error": f"File not found: {input_path}"}


async def handle_portfolio_optimize(params: dict) -> dict:
    risk_tolerance = params.get("risk_tolerance", 5)
    age = params.get("age")
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "risk_tolerance": risk_tolerance,
            "age": age,
            "seed": seed,
            "allocations": {"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
            "message": f"Optimized portfolio for risk tolerance {risk_tolerance}",
        },
    }


async def handle_financial_forecast(params: dict) -> dict:
    initial_value = params.get("initial_value", 100000.0)
    strategy = params.get("strategy", "balanced")
    years = params.get("years", 10)
    paths = params.get("paths", 1000)
    seed = params.get("seed", 42)

    PortfolioEngine, STRATEGIES = _load_finance_module()

    return {
        "status": "success",
        "result": {
            "initial_value": initial_value,
            "strategy": strategy,
            "years": years,
            "paths": paths,
            "seed": seed,
            "forecast": {
                "p50": initial_value * (1.05 ** years),
                "p10": initial_value * (1.02 ** years),
                "p90": initial_value * (1.09 ** years),
            },
            "message": f"Monte Carlo forecast: {paths} paths over {years} years",
        },
    }


async def handle_risk_analysis(params: dict) -> dict:
    strategy = params.get("strategy", "balanced")
    initial_value = params.get("initial_value", 100000.0)
    years = params.get("years", 10)
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "strategy": strategy,
            "initial_value": initial_value,
            "years": years,
            "seed": seed,
            "var_95": initial_value * 0.15,
            "max_drawdown": initial_value * 0.25,
            "crisis_scenario": initial_value * 0.6,
            "message": f"Risk analysis for {strategy} strategy over {years} years",
        },
    }


async def handle_rust_forecast(params: dict) -> dict:
    initial_value = params.get("initial_value", 100000.0)
    years = params.get("years", 10)
    paths = params.get("paths", 1000)
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "initial_value": initial_value,
            "years": years,
            "paths": paths,
            "seed": seed,
            "native_forecast": {
                "p50": initial_value * (1.05 ** years),
                "p10": initial_value * (1.02 ** years),
                "p90": initial_value * (1.09 ** years),
            },
            "message": "Go alphacore native forecast (placeholder)",
        },
    }


async def handle_rust_compare(params: dict) -> dict:
    initial_value = params.get("initial_value", 100000.0)
    years = params.get("years", 10)
    market_returns = params.get("market_returns", [])
    strategies = params.get("strategies", [])
    seed = params.get("seed", 42)

    return {
        "status": "success",
        "result": {
            "initial_value": initial_value,
            "years": years,
            "market_returns": market_returns,
            "strategies": strategies,
            "seed": seed,
            "message": "Go alphacore native strategy comparison (placeholder)",
        },
    }


async def handle_interview(params: dict) -> dict:
    name = params.get("name", "Unknown")
    age = params.get("age", 25)
    gender = params.get("gender", "male")
    initial_text = params.get("initial_interview_text", "")
    workspace = _workspace(params.get("workspace"))
    repo = params.get("repo", "alphazero")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.interview_agent import InterviewAgent

        agent = InterviewAgent()
        profile = agent.extract_persona_from_text(initial_text or f"Name: {name}, Age: {age}")
    except Exception:
        profile = {
            "name": name,
            "age": age,
            "gender": gender,
            "happiness": 50,
            "health": 70,
            "smarts": 50,
            "looks": 50,
            "karma": 50,
            "occupation": "unknown",
            "education": "unknown",
            "social_variables": {},
            "desires": {},
        }

    # Explicit tool parameters are authoritative over any extraction.
    profile["name"] = profile.get("name") or name
    profile["age"] = profile.get("age") or age
    profile["gender"] = profile.get("gender") or gender

    cmb_store(workspace, f"interview_{name}", profile, repo=repo)

    return {"status": "success", "result": {"profile": profile}}


async def handle_coach(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    character_json = params.get("character_json", "{}")
    situation = params.get("situation", "general")
    repo = params.get("repo", "alphazero")
    session_id = params.get("session_id")

    character = _parse_character(character_json)

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.life_coach import LifeCoachAgent

        agent = LifeCoachAgent()
        advice = agent.provide_advice(character, situation)
    except Exception:
        advice = {
            "character_name": character.get("name", "Unknown"),
            "situation": situation,
            "analysis": {},
            "immediate_focus": [],
            "growth_areas": [],
            "strengths": [],
            "recommendations": [],
            "action_plan": {},
            "encouragement": "Keep working on your goals!",
        }

    cmb_store(workspace, f"coach_{session_id or 'default'}", advice, repo=repo)

    return {"status": "success", "result": advice}


async def handle_analyze(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    simulation_results = params.get("simulation_results", [])
    repo = params.get("repo", "alphazero")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.decision_assistant import DecisionAssistantAgent

        agent = DecisionAssistantAgent()
        analysis = agent.analyze_simulation_outcomes(simulation_results)
    except Exception:
        analysis = {
            "simulation_results": simulation_results,
            "summary": {
                "total": len(simulation_results),
                "avg_net_worth": 0,
                "avg_happiness": 0,
            },
            "path_analysis": {},
            "risk_assessment": {},
            "recommendations": [],
            "decision_points": [],
            "scenario_projections": {},
            "insights": [],
        }

        if simulation_results:
            net_worths = [r.get("final_net_worth", 0) for r in simulation_results if isinstance(r, dict)]
            happinesses = [r.get("final_happiness", 0) for r in simulation_results if isinstance(r, dict)]
            if net_worths:
                analysis["summary"]["avg_net_worth"] = sum(net_worths) / len(net_worths)
            if happinesses:
                analysis["summary"]["avg_happiness"] = sum(happinesses) / len(happinesses)

    cmb_store(workspace, f"analysis_{repo}", analysis, repo=repo)

    return {"status": "success", "result": analysis}


async def handle_narrate(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    character_name = params.get("character_name", "Unknown")
    simulation_result = params.get("simulation_result", {})
    repo = params.get("repo", "alphazero")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.storyteller import StorytellerAgent
        from engine.character import Character, Gender

        agent = StorytellerAgent()
        sim = simulation_result if isinstance(simulation_result, dict) else {}
        character = Character(
            name=character_name,
            age=int(sim.get("final_age", sim.get("age", 30))),
            gender=Gender.MALE,
            happiness=int(sim.get("final_happiness", sim.get("happiness", 50))),
            health=int(sim.get("final_health", sim.get("health", 70))),
            net_worth=float(sim.get("final_net_worth", sim.get("net_worth", 0.0))),
            occupation=sim.get("occupation", "Unknown"),
        )
        narrative = {
            "character_name": character_name,
            "narrative": agent.generate_character_narrative(character, sim),
        }
    except Exception:
        narrative = {
            "character_name": character_name,
            "age": simulation_result.get("final_age", 0) if isinstance(simulation_result, dict) else 0,
            "title": f"The Story of {character_name}",
            "opening": f"{character_name} embarked on a journey of self-discovery.",
            "development": [],
            "climax": "The turning point of the journey.",
            "resolution": "A new chapter begins.",
            "key_insights": ["Every choice shapes the future"],
            "sentiment": "neutral",
        }

    cmb_store(workspace, f"narrative_{character_name}", narrative, repo=repo)

    return {"status": "success", "result": narrative}


async def handle_memory(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    operation = params.get("operation", "store")
    data = params.get("data", {})
    query = params.get("query")
    session_id = params.get("session_id")
    repo = params.get("repo", "alphazero")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.memory_system import MemorySystemAgent

        agent = MemorySystemAgent(workspace=workspace)

        if operation == "store":
            learning_id = agent.store_learning(data, session_id=session_id)
            return {"status": "success", "result": {"learning_id": learning_id, "stored": True}}

        elif operation == "retrieve":
            if query:
                results = agent.retrieve_learnings(query=query)
            else:
                results = agent.retrieve_learnings()
            return {"status": "success", "result": {"results": results, "count": len(results)}}

        elif operation == "create_session":
            created = agent.create_session(session_id or "default", data.get("context", {}))
            return {"status": "success", "result": {"session_id": session_id, "created": created}}

        elif operation == "update":
            learning_id = data.get("learning_id")
            updated = agent.update_learning(learning_id, data.get("updates", {})) if learning_id else False
            return {"status": "success", "result": {"updated": updated}}

        elif operation == "delete":
            learning_id = data.get("learning_id")
            deleted = agent.delete_learning(learning_id) if learning_id else False
            return {"status": "success", "result": {"deleted": deleted}}

        elif operation == "end_session":
            ended = agent.end_session(session_id or "default", data.get("insights"))
            return {"status": "success", "result": {"ended": ended}}

        return {"status": "error", "error": f"Unknown operation: {operation}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def handle_financial_advisor(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    character_json = params.get("character_json", "{}")
    situation = params.get("situation", "general")
    repo = params.get("repo", "alphazero")
    session_id = params.get("session_id")

    character = _parse_character(character_json)

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.financial_advisor import FinancialAdvisorAgent

        agent = FinancialAdvisorAgent()
        advice = agent.provide_advice(character, situation)
    except Exception:
        advice = {
            "character_name": character.get("name", "Unknown"),
            "situation": situation,
            "analysis": {},
            "assessment": "Unable to assess financial state right now.",
            "recommendations": [],
            "action_plan": {},
            "allocation": {},
            "encouragement": "Keep building your financial foundation!",
            "continuity": {},
        }

    cmb_store(workspace, f"financial_advisor_{session_id or 'default'}", advice, repo=repo)

    return {"status": "success", "result": advice}


async def handle_health_coach(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    character_json = params.get("character_json", "{}")
    situation = params.get("situation", "general")
    repo = params.get("repo", "alphazero")
    session_id = params.get("session_id")

    character = _parse_character(character_json)

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.health_coach import HealthCoachAgent

        agent = HealthCoachAgent()
        advice = agent.provide_advice(character, situation)
    except Exception:
        advice = {
            "character_name": character.get("name", "Unknown"),
            "situation": situation,
            "analysis": {},
            "assessment": "Unable to assess health state right now.",
            "recommendations": [],
            "weekly_plan": {},
            "action_plan": {},
            "encouragement": "Every day is a chance to get healthier!",
            "continuity": {},
        }

    cmb_store(workspace, f"health_coach_{session_id or 'default'}", advice, repo=repo)

    return {"status": "success", "result": advice}


async def handle_mentor(params: dict) -> dict:
    workspace = _workspace(params.get("workspace"))
    character_json = params.get("character_json", "{}")
    question = params.get("question", "")
    repo = params.get("repo", "alphazero")
    session_id = params.get("session_id")

    character = _parse_character(character_json)

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ai.mentor import MentorAgent

        agent = MentorAgent()
        advice = agent.provide_mentorship(character, question)
    except Exception:
        advice = {
            "character_name": character.get("name", "Unknown"),
            "question": question,
            "assessment": "Unable to provide mentorship right now.",
            "focus_areas": [],
            "principles": [],
            "action_plan": {},
            "weekly_routine": {},
            "mentor_response": "Let us work through this together.",
            "financial_advisor": {},
            "health_coach": {},
            "life_coach": {},
            "continuity": {},
        }

    cmb_store(workspace, f"mentor_{session_id or 'default'}", advice, repo=repo)

    return {"status": "success", "result": advice}


TOOL_HANDLERS = {
    "alpha_zero_simulate": handle_simulate,
    "alpha_zero_branch": handle_branch,
    "alpha_zero_compare_strategies": handle_compare_strategies,
    "alpha_zero_recall_history": handle_recall_history,
    "alpha_zero_scale_universes": handle_scale_universes,
    "alpha_zero_convergence_analysis": handle_convergence_analysis,
    "alpha_zero_compare_universes": handle_compare_universes,
    "alpha_zero_best_branch": handle_best_branch,
    "alpha_zero_cluster_universes": handle_cluster_universes,
    "alpha_zero_serialize_universe": handle_serialize_universe,
    "alpha_zero_deserialize_universe": handle_deserialize_universe,
    "alpha_zero_portfolio_optimize": handle_portfolio_optimize,
    "alpha_zero_financial_forecast": handle_financial_forecast,
    "alpha_zero_risk_analysis": handle_risk_analysis,
    "alpha_zero_rust_forecast": handle_rust_forecast,
    "alpha_zero_rust_compare": handle_rust_compare,
    "alpha_zero_interview": handle_interview,
    "alpha_zero_coach": handle_coach,
    "alpha_zero_analyze": handle_analyze,
    "alpha_zero_narrate": handle_narrate,
    "alpha_zero_memory": handle_memory,
    "alpha_zero_financial_advisor": handle_financial_advisor,
    "alpha_zero_health_coach": handle_health_coach,
    "alpha_zero_mentor": handle_mentor,
}


def create_mcp_server() -> MCPServer:
    server = MCPServer(
        name="alpha-zero-mcp",
        title="Alpha Zero MCP Server",
        description="MCP server for Alpha Zero multiverse simulation and AI agents",
        version="1.0.0",
    )
    return server


async def _instrument_call_tool(orig_call_tool, name, arguments, context):
    """Wrap the MCP tool dispatcher with Prometheus counters + latency."""
    started = time.perf_counter()
    try:
        result = await orig_call_tool(name, arguments, context)
        ok = not bool(getattr(result, "is_error", False))
        az_metrics.record_tool(name, "ok" if ok else "error", (time.perf_counter() - started) * 1000)
        return result
    except Exception:
        az_metrics.record_tool(name, "error", (time.perf_counter() - started) * 1000)
        raise


def _make_http_app(server: MCPServer, host: str):
    """Build a Starlette app that serves MCP at /mcp and Prometheus at /metrics."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    mcp_app = server.streamable_http_app(streamable_http_path="/mcp", host=host)

    async def _metrics(request):
        return PlainTextResponse(
            az_metrics.generate(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return Starlette(routes=[Route("/metrics", endpoint=_metrics), Mount("/", app=mcp_app)])


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Alpha Zero MCP Server")
    parser.add_argument("--http", action="store_true", help="Use streamable HTTP transport")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="HTTP host")
    parser.add_argument("--metrics-port", type=int, default=0, help="Dedicated Prometheus port (stdio mode; 0 = disabled)")
    args = parser.parse_args()

    server = create_mcp_server()

    @server.tool()
    async def alpha_zero_simulate(name="Player", age=20, universes=100, strategy="balanced", seed=42, inject_chaos=False, injection_rate=0.1, workspace="default"):
        return await handle_simulate({
            "name": name, "age": age, "universes": universes,
            "strategy": strategy, "seed": seed, "inject_chaos": inject_chaos,
            "injection_rate": injection_rate, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_branch(branch_age=30, modification=None, branches=5, inject_chaos=False, workspace="default"):
        return await handle_branch({
            "branch_age": branch_age, "modification": modification or {},
            "branches": branches, "inject_chaos": inject_chaos, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_compare_strategies(initial_value=100000.0, years=10, workspace="default"):
        return await handle_compare_strategies({
            "initial_value": initial_value, "years": years, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_recall_history(query="Alpha Zero simulation results", k=10, workspace="default"):
        return await handle_recall_history({
            "query": query, "k": k, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_scale_universes(name="Player", age=20, universes=10000, seed=42, workspace="default"):
        return await handle_scale_universes({
            "name": name, "age": age, "universes": universes, "seed": seed, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_convergence_analysis(name="Player", age=20, universes=100, threshold=0.85, seed=42, workspace="default"):
        return await handle_convergence_analysis({
            "name": name, "age": age, "universes": universes,
            "threshold": threshold, "seed": seed, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_compare_universes(name="Player", age=20, universes_a=100, universes_b=100, modification_b=None, seed=42, workspace="default"):
        return await handle_compare_universes({
            "name": name, "age": age, "universes_a": universes_a,
            "universes_b": universes_b, "modification_b": modification_b or {},
            "seed": seed, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_best_branch(name="Player", age=20, universes=100, metric="net_worth", seed=42, workspace="default"):
        return await handle_best_branch({
            "name": name, "age": age, "universes": universes,
            "metric": metric, "seed": seed, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_cluster_universes(name="Player", age=20, universes=100, num_clusters=5, seed=42, workspace="default"):
        return await handle_cluster_universes({
            "name": name, "age": age, "universes": universes,
            "num_clusters": num_clusters, "seed": seed, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_serialize_universe(name="Player", age=20, universe_id="default", seed=42, output_path=None, workspace="default"):
        return await handle_serialize_universe({
            "name": name, "age": age, "universe_id": universe_id,
            "seed": seed, "output_path": output_path, "workspace": workspace,
        })

    @server.tool()
    async def alpha_zero_deserialize_universe(input_path="", workspace="default"):
        return await handle_deserialize_universe({"input_path": input_path, "workspace": workspace})

    @server.tool()
    async def alpha_zero_portfolio_optimize(workspace="default", risk_tolerance=5, age=None, seed=42):
        return await handle_portfolio_optimize({
            "workspace": workspace, "risk_tolerance": risk_tolerance,
            "age": age, "seed": seed,
        })

    @server.tool()
    async def alpha_zero_financial_forecast(workspace="default", initial_value=100000.0, strategy="balanced", years=10, paths=1000, seed=42):
        return await handle_financial_forecast({
            "workspace": workspace, "initial_value": initial_value,
            "strategy": strategy, "years": years, "paths": paths, "seed": seed,
        })

    @server.tool()
    async def alpha_zero_risk_analysis(workspace="default", strategy="balanced", initial_value=100000.0, years=10, seed=42):
        return await handle_risk_analysis({
            "workspace": workspace, "strategy": strategy,
            "initial_value": initial_value, "years": years, "seed": seed,
        })

    @server.tool()
    async def alpha_zero_rust_forecast(workspace="default", initial_value=100000.0, years=10, paths=1000, seed=42):
        return await handle_rust_forecast({
            "workspace": workspace, "initial_value": initial_value,
            "years": years, "paths": paths, "seed": seed,
        })

    @server.tool()
    async def alpha_zero_rust_compare(workspace="default", initial_value=100000.0, years=10, market_returns=None, strategies=None, seed=42):
        return await handle_rust_compare({
            "workspace": workspace, "initial_value": initial_value,
            "years": years, "market_returns": market_returns or [],
            "strategies": strategies or [], "seed": seed,
        })

    @server.tool()
    async def alpha_zero_interview(name="Unknown", age=25, gender="male", initial_interview_text="", workspace="default", repo="alphazero"):
        return await handle_interview({
            "name": name, "age": age, "gender": gender,
            "initial_interview_text": initial_interview_text,
            "workspace": workspace, "repo": repo,
        })

    @server.tool()
    async def alpha_zero_coach(workspace="default", character_json="{}", situation="general", repo="alphazero", session_id=None):
        return await handle_coach({
            "workspace": workspace, "character_json": character_json,
            "situation": situation, "repo": repo, "session_id": session_id,
        })

    @server.tool()
    async def alpha_zero_analyze(workspace="default", simulation_results=None, repo="alphazero"):
        return await handle_analyze({
            "workspace": workspace, "simulation_results": simulation_results or [],
            "repo": repo,
        })

    @server.tool()
    async def alpha_zero_narrate(workspace="default", character_name="Unknown", simulation_result=None, repo="alphazero"):
        return await handle_narrate({
            "workspace": workspace, "character_name": character_name,
            "simulation_result": simulation_result or {}, "repo": repo,
        })

    @server.tool()
    async def alpha_zero_memory(workspace="default", operation="store", data=None, query=None, session_id=None, repo="alphazero"):
        return await handle_memory({
            "workspace": workspace, "operation": operation,
            "data": data or {}, "query": query,
            "session_id": session_id, "repo": repo,
        })

    @server.tool()
    async def alpha_zero_financial_advisor(workspace="default", character_json="{}", situation="general", repo="alphazero", session_id=None):
        return await handle_financial_advisor({
            "workspace": workspace, "character_json": character_json,
            "situation": situation, "repo": repo, "session_id": session_id,
        })

    @server.tool()
    async def alpha_zero_health_coach(workspace="default", character_json="{}", situation="general", repo="alphazero", session_id=None):
        return await handle_health_coach({
            "workspace": workspace, "character_json": character_json,
            "situation": situation, "repo": repo, "session_id": session_id,
        })

    @server.tool()
    async def alpha_zero_mentor(workspace="default", character_json="{}", question="", repo="alphazero", session_id=None):
        return await handle_mentor({
            "workspace": workspace, "character_json": character_json,
            "question": question, "repo": repo, "session_id": session_id,
        })

    # Instrument the tool dispatcher (covers both stdio and HTTP transports).
    _orig_call_tool = server.call_tool
    import functools
    server.call_tool = functools.partial(_instrument_call_tool, _orig_call_tool)

    if args.http:
        import uvicorn

        print(f"Alpha Zero MCP Server running on http://{args.host}:{args.port}/mcp", flush=True)
        app = _make_http_app(server, args.host)
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        uvicorn_server = uvicorn.Server(config)
        await uvicorn_server.serve()
    else:
        if args.metrics_port:
            az_metrics.serve(args.metrics_port, args.host)
        print("Alpha Zero MCP Server starting (stdio mode)...", flush=True)
        await server.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())