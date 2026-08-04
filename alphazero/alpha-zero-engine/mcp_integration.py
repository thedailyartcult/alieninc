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
}
