"""Shared Monte Carlo branching primitive.

Lifted from Alpha Zero's ``engine/monte_carlo.py`` — the core idea of running N
parallel universes and aggregating which branch "won." Every station uses this:
Alpha Zero branches life decisions, Kriegspiel branches battlefield scenarios,
CC branches infra failure paths, Remnants branches post-conflict states.

This module provides the lightweight, dependency-free primitive. The full Alpha
Zero engine (with character simulation, portfolio tracking, etc.) lives at
``/home/alieninc/alphazero/alpha-zero-engine/`` and is imported directly by the
gateway when available.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Optional


def branch_factor(universes: int, chaos: bool = False) -> float:
    """Estimate branching breadth for a given universe count.

    When chaos injection is enabled (Phase 2), each universe diverges further,
    so the effective branch count is higher than the nominal universe count.
    """
    base = float(universes)
    if chaos:
        return base * (1.0 + random.random() * 0.3)
    return base


def monte_carlo_branch(
    simulate_one: Callable[[int], dict[str, Any]],
    universes: int,
    seed: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Run ``simulate_one(seed_i)`` for ``universes`` parallel branches.

    ``simulate_one`` returns a dict with at least ``{"outcome": ..., "score": ...}``.
    Returns the list of all branch results. The caller aggregates (best branch,
    convergence, survivors, etc.) — see ``ScenarioResult``.
    """
    rng = random.Random(seed)
    results: list[dict[str, Any]] = []
    for i in range(universes):
        branch_seed = rng.randint(0, 2**31 - 1)
        results.append(simulate_one(branch_seed))
    return results


def best_branch(branches: list[dict[str, Any]], key: str = "score") -> Optional[dict[str, Any]]:
    """Pick the winning branch by highest ``key`` value."""
    if not branches:
        return None
    return max(branches, key=lambda b: b.get(key, float("-inf")))


def convergence_rate(branches: list[dict[str, Any]], outcome_key: str = "outcome") -> float:
    """Fraction of branches that agree on the most common outcome."""
    if not branches:
        return 0.0
    counts: dict[Any, int] = {}
    for b in branches:
        o = b.get(outcome_key)
        counts[o] = counts.get(o, 0) + 1
    top = max(counts.values())
    return top / len(branches)
