"""MCP Server integration — simulation state persistence via CMB memory tools.

This module provides functions to store and recall Alpha Zero simulation
results through the CMB memory system, enabling cross-session persistence
and agent-accessible simulation history.
"""

from __future__ import annotations

import json
from typing import Optional


def store_simulation_result(
    workspace: str,
    result: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> str:
    """
    Store a simulation result as a CMB memory.

    Args:
        workspace: CMB workspace
        result: Simulation result dict (from run_multiverse or run_single)
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory ID string
    """
    # This function is designed to be called via the CMB MCP tools
    # The actual implementation uses cmb_remember through the MCP protocol
    content = json.dumps({
        "type": "simulation_result",
        "mode": result.get("mode", "unknown"),
        "total_simulations": result.get("total_simulations", 0),
        "convergence_rate": result.get("convergence_rate", 0),
        "sharpe_ratio": result.get("sharpe_ratio", 0),
        "best_net_worth": result.get("best_net_worth", {}).get("final_net_worth", 0),
        "best_happiness": result.get("best_happiness", {}).get("final_happiness", 0),
        "outcome_distribution": result.get("outcome_distribution", {}),
        "metrics": result.get("metrics", {}),
    }, indent=2)

    title = f"Simulation: {result.get('mode', 'unknown')} — {result.get('total_simulations', 0)} universes"

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": title,
        "mtype": "episodic",
        "session_id": session_id,
        "keywords": ["simulation", "multiverse", "alpha-zero", "monte-carlo"],
    }


def store_character_state(
    workspace: str,
    character: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store a character state snapshot as a CMB memory.

    Args:
        workspace: CMB workspace
        character: Character state dict (from character.to_dict())
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "character_state",
        "name": character.get("name"),
        "age": character.get("age"),
        "year": character.get("year"),
        "happiness": character.get("happiness"),
        "health": character.get("health"),
        "smarts": character.get("smarts"),
        "looks": character.get("looks"),
        "karma": character.get("karma"),
        "net_worth": character.get("net_worth"),
        "portfolio_value": character.get("portfolio_value"),
        "is_alive": character.get("is_alive"),
        "universe_id": character.get("universe_id"),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Character: {character.get('name')} — Age {character.get('age')}, Universe {character.get('universe_id')}",
        "mtype": "semantic",
        "session_id": session_id,
        "keywords": ["character", "state", "alpha-zero"],
    }


def store_portfolio_comparison(
    workspace: str,
    comparison: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store a portfolio strategy comparison as a CMB memory.

    Args:
        workspace: CMB workspace
        comparison: Strategy comparison dict
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    strategies_summary = []
    for name, data in comparison.get("strategies", {}).items():
        strategies_summary.append(
            f"- {data['name']}: ${data['final_value']:,.2f} ({data['total_return_pct']:.1f}% return)"
        )

    content = f"Portfolio Strategy Comparison:\n" + "\n".join(strategies_summary)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Portfolio Comparison — {len(comparison.get('strategies', {}))} strategies",
        "mtype": "semantic",
        "session_id": session_id,
        "keywords": ["portfolio", "strategy", "comparison", "finance"],
    }


def recall_simulation_history(
    workspace: str,
    repo: str = "alphazero",
    k: int = 10,
) -> str:
    """
    Query to recall simulation history from CMB memory.

    Returns a query string for cmb_recall.
    """
    return "Alpha Zero simulation results"


def recall_best_universes(
    workspace: str,
    repo: str = "alphazero",
    k: int = 5,
) -> str:
    """
    Query to recall best-performing universes from CMB memory.

    Returns a query string for cmb_recall.
    """
    return "best performing parallel universes highest net worth"


# ─── AI Agent Integration ──────────────────────────────────────────────────────

def store_interview_profile(
    workspace: str,
    profile: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store an AI interview profile and generated character data.

    Args:
        workspace: CMB workspace
        profile: Interview profile with name, age, gender, and social variables
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "interview_profile",
        "name": profile.get("name"),
        "age": profile.get("age"),
        "gender": profile.get("gender"),
        "happiness": profile.get("happiness"),
        "health": profile.get("health"),
        "smarts": profile.get("smarts"),
        "looks": profile.get("looks"),
        "karma": profile.get("karma"),
        "occupation": profile.get("occupation"),
        "education": profile.get("education"),
        "social_variables": profile.get("social_variables", {}),
        "desires": profile.get("desires", {}),
        "inferred_traits": profile.get("inferred_traits", []),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Interview Profile: {profile.get('name', 'Unknown')} — Age {profile.get('age', 'N/A')}",
        "mtype": "semantic",
        "session_id": session_id,
        "keywords": ["interview", "profile", "character", "social_variables", "ai_agent"],
    }


def store_coaching_advice(
    workspace: str,
    advice: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store AI coaching advice and recommendations.

    Args:
        workspace: CMB workspace
        advice: Coaching data with analysis and recommendations
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "coaching_advice",
        "character_name": advice.get("character_name"),
        "situation": advice.get("situation"),
        "analysis": advice.get("analysis", {}),
        "immediate_focus": advice.get("immediate_focus", []),
        "growth_areas": advice.get("growth_areas", []),
        "strengths": advice.get("strengths", []),
        "recommendations": advice.get("recommendations", []),
        "action_plan": advice.get("action_plan", {}),
        "encouragement": advice.get("encouragement"),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Coaching Advice for {advice.get('character_name', 'Unknown')}",
        "mtype": "procedural",
        "session_id": session_id,
        "keywords": ["coaching", "advice", "recommendations", "life_coach", "ai_agent"],
    }


def store_decision_analysis(
    workspace: str,
    analysis: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store AI decision analysis and insights.

    Args:
        workspace: CMB workspace
        analysis: Decision analysis with outcomes and recommendations
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "decision_analysis",
        "simulation_results": analysis.get("simulation_results", []),
        "summary": analysis.get("summary", {}),
        "path_analysis": analysis.get("path_analysis", {}),
        "risk_assessment": analysis.get("risk_assessment", {}),
        "recommendations": analysis.get("recommendations", []),
        "decision_points": analysis.get("decision_points", []),
        "scenario_projections": analysis.get("scenario_projections", {}),
        "insights": analysis.get("insights", []),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Decision Analysis — {len(analysis.get('simulation_results', []))} scenarios",
        "mtype": "semantic",
        "session_id": session_id,
        "keywords": ["decision", "analysis", "insights", "assistant", "ai_agent"],
    }


def store_narrative(
    workspace: str,
    narrative: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store AI-generated narrative and story from simulation data.

    Args:
        workspace: CMB workspace
        narrative: Generated narrative with story components
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "narrative",
        "character_name": narrative.get("character_name"),
        "age": narrative.get("age"),
        "title": narrative.get("title"),
        "opening": narrative.get("opening"),
        "development": narrative.get("development", []),
        "climax": narrative.get("climax"),
        "resolution": narrative.get("resolution"),
        "key_insights": narrative.get("key_insights", []),
        "sentiment": narrative.get("sentiment", "neutral"),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Narrative: {narrative.get('title', 'Untitled')}",
        "mtype": "episodic",
        "session_id": session_id,
        "keywords": ["narrative", "story", "character", "storyteller", "ai_agent"],
    }


def store_learning(
    workspace: str,
    learning: dict,
    repo: str = "alphazero",
    session_id: str = None,
) -> dict:
    """
    Store AI learning and knowledge across sessions.

    Args:
        workspace: CMB workspace
        learning: Learning data with patterns and insights
        repo: Repository scope
        session_id: Optional session ID

    Returns:
        Memory payload dict
    """
    content = json.dumps({
        "type": "learning",
        "learning_id": learning.get("learning_id"),
        "timestamp": learning.get("timestamp"),
        "data": learning.get("data", {}),
        "tags": learning.get("tags", []),
        "importance": learning.get("importance", 0),
        "source": learning.get("source", "ai_agent"),
        "patterns": learning.get("patterns", []),
        "knowledge_graph": learning.get("knowledge_graph", {}),
        "applications": learning.get("applications", []),
    }, indent=2)

    return {
        "workspace": workspace,
        "repo": repo,
        "content": content,
        "title": f"Learning: {learning.get('learning_id', 'Unknown')}",
        "mtype": "semantic",
        "session_id": session_id,
        "keywords": ["learning", "knowledge", "memory", "memory_system", "ai_agent"],
    }


# ─── MCP Tool Definitions ────────────────────────────────────────────────────
# These can be added to the MCP server's tool registry

ALPHA_ZERO_TOOLS = {
    "alpha_zero_simulate": {
        "description": "Run an Alpha Zero multiverse simulation and store results in memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes": {"type": "integer", "description": "Number of parallel universes"},
                "strategy": {"type": "string", "description": "Portfolio strategy"},
                "seed": {"type": "integer", "description": "Random seed"},
                "inject_chaos": {"type": "boolean", "description": "Enable chaotic micro-variable injection"},
                "injection_rate": {"type": "number", "description": "Probability of chaos injection per variable"},
            },
        },
    },
    "alpha_zero_branch": {
        "description": "Branch from a specific age point with modified conditions.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch_age": {"type": "integer", "description": "Age to branch from"},
                "modification": {"type": "object", "description": "Attribute modifications"},
                "branches": {"type": "integer", "description": "Number of branches"},
                "inject_chaos": {"type": "boolean", "description": "Enable chaotic micro-variable injection"},
            },
        },
    },
    "alpha_zero_compare_strategies": {
        "description": "Compare portfolio strategies and store results.",
        "parameters": {
            "type": "object",
            "properties": {
                "initial_value": {"type": "number", "description": "Initial portfolio value"},
                "years": {"type": "integer", "description": "Simulation years"},
            },
        },
    },
    "alpha_zero_recall_history": {
        "description": "Recall previous simulation results from memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to recall"},
                "k": {"type": "integer", "description": "Max results"},
            },
        },
    },
    "alpha_zero_scale_universes": {
        "description": "Scale simulation to 10,000+ parallel universes with chaotic micro-variable injection.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes": {"type": "integer", "description": "Number of parallel universes (10,000+)"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_convergence_analysis": {
        "description": "Analyze convergence probability across parallel universes with configurable threshold.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes": {"type": "integer", "description": "Number of parallel universes"},
                "threshold": {"type": "number", "description": "Convergence threshold (0.0-1.0, default 0.85)"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_compare_universes": {
        "description": "Compare two groups of universes side-by-side (e.g., with/without a modification).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes_a": {"type": "integer", "description": "Number of universes in group A"},
                "universes_b": {"type": "integer", "description": "Number of universes in group B"},
                "modification_b": {"type": "object", "description": "Modifications for group B"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_best_branch": {
        "description": "Surface the best-performing branch across all universes by a given metric.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes": {"type": "integer", "description": "Number of parallel universes"},
                "metric": {"type": "string", "description": "Metric to optimize: 'net_worth', 'happiness', or 'convergence'"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_cluster_universes": {
        "description": "Group similar universe outcomes into clusters and surface representative branches.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universes": {"type": "integer", "description": "Number of parallel universes"},
                "num_clusters": {"type": "integer", "description": "Number of clusters to form"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_serialize_universe": {
        "description": "Save a universe state to a JSON file for save/load capability.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "universe_id": {"type": "string", "description": "Universe ID to serialize"},
                "seed": {"type": "integer", "description": "Random seed"},
                "output_path": {"type": "string", "description": "Output file path"},
            },
        },
    },
    "alpha_zero_deserialize_universe": {
        "description": "Load a previously serialized universe state from a JSON file.",
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string", "description": "Path to serialized universe JSON file"},
            },
        },
    },
    "alpha_zero_portfolio_optimize": {
        "description": "Optimize portfolio allocations for a risk tolerance or age-based glide path.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "risk_tolerance": {"type": "integer", "description": "0 (very safe) to 10 (aggressive)"},
                "age": {"type": "integer", "description": "If set, use lifecycle glide path"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_financial_forecast": {
        "description": "Monte Carlo forecast of portfolio value with percentile bands.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "initial_value": {"type": "number", "description": "Starting portfolio value"},
                "strategy": {"type": "string", "description": "Portfolio strategy"},
                "years": {"type": "integer", "description": "Forecast horizon in years"},
                "paths": {"type": "integer", "description": "Number of Monte Carlo paths"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_risk_analysis": {
        "description": "Stress test a portfolio strategy: VaR, drawdown, crisis scenarios.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "strategy": {"type": "string", "description": "Portfolio strategy to analyze"},
                "initial_value": {"type": "number", "description": "Portfolio value to stress"},
                "years": {"type": "integer", "description": "Simulation years for VaR"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_rust_forecast": {
        "description": "Run Go alphacore native forecast simulation with Rust client integration.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "initial_value": {"type": "number", "description": "Starting portfolio value"},
                "years": {"type": "integer", "description": "Forecast horizon in years"},
                "paths": {"type": "integer", "description": "Number of Monte Carlo paths"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_rust_compare": {
        "description": "Run Go alphacore native strategy comparison with Rust client integration.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "initial_value": {"type": "number", "description": "Starting portfolio value"},
                "years": {"type": "integer", "description": "Simulation years"},
                "market_returns": {"type": "array", "items": {"type": "number"}, "description": "Market returns array"},
                "strategies": {"type": "array", "description": "Array of strategy specs"},
                "seed": {"type": "integer", "description": "Random seed"},
            },
        },
    },
    "alpha_zero_interview": {
        "description": "Conduct AI personality interview and generate character profile with 34 social variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name"},
                "age": {"type": "integer", "description": "Starting age"},
                "gender": {"type": "string", "description": "Gender (male, female, non_binary)"},
                "initial_interview_text": {"type": "string", "description": "Initial interview message to start personality profiling"},
                "workspace": {"type": "string", "description": "CMB workspace"},
                "repo": {"type": "string", "description": "Repository scope"},
            },
        },
    },
    "alpha_zero_coach": {
        "description": "Provide AI life coaching advice based on character state and simulation outcomes.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "character_json": {"type": "string", "description": "Character state as JSON string"},
                "situation": {"type": "string", "description": "Life situation to provide coaching for"},
                "repo": {"type": "string", "description": "Repository scope"},
                "session_id": {"type": "string", "description": "Session ID"},
            },
        },
    },
    "alpha_zero_analyze": {
        "description": "Analyze simulation outcomes and provide strategic decision guidance.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "simulation_results": {"type": "array", "description": "Array of simulation result objects"},
                "repo": {"type": "string", "description": "Repository scope"},
            },
        },
    },
    "alpha_zero_narrate": {
        "description": "Generate compelling narratives and life stories from simulation data.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "character_name": {"type": "string", "description": "Character name"},
                "simulation_result": {"type": "object", "description": "Single simulation result object"},
                "repo": {"type": "string", "description": "Repository scope"},
            },
        },
    },
    "alpha_zero_memory": {
        "description": "Store, retrieve, and manage AI learnings across sessions with retention policies.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "CMB workspace"},
                "operation": {"type": "string", "description": "Operation: 'store', 'retrieve', 'update', 'delete', 'create_session'"},
                "data": {"type": "object", "description": "Data payload for the operation"},
                "query": {"type": "string", "description": "Search query for retrieval operations"},
                "session_id": {"type": "string", "description": "Session ID"},
                "repo": {"type": "string", "description": "Repository scope"},
            },
        },
    },
}
