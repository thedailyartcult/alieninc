"""Platoon objective-capture engine — define the starting condition.

An ``Objective`` is the single seed that flows through the entire 7-product
pipeline. Platoon captures it from the enterprise client, structures it, and
runs Monte Carlo branches across plausible framings — different constraint
weights, different success criteria, different risk tolerances — to see how
the objective's definition shapes the downstream outcomes.

This is the input layer. Without Platoon, the rest of the stack has nothing
to simulate.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate


class ObjectiveDomain(str, Enum):
    """The domain the objective operates in."""

    NATIONAL_SECURITY = "national_security"
    ECONOMIC_POLICY = "economic_policy"
    CORPORATE_STRATEGY = "corporate_strategy"
    INFRASTRUCTURE = "infrastructure"
    PUBLIC_HEALTH = "public_health"
    ENERGY_TRANSITION = "energy_transition"
    SUPPLY_CHAIN = "supply_chain"
    CYBERSECURITY = "cybersecurity"
    DIPLOMACY = "diplomacy"
    MARKET_ENTRY = "market_entry"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class Objective:
    """The structured starting condition for the entire pipeline."""

    title: str
    domain: ObjectiveDomain
    goal: str                             # what success looks like, in one sentence
    constraints: list[str] = field(default_factory=list)   # things that can't be violated
    success_criteria: list[str] = field(default_factory=list)  # measurable outcomes
    risk_tolerance: RiskTolerance = RiskTolerance.BALANCED
    time_horizon_years: float = 5.0       # how far out to project
    population_scale: float = 50.0        # 0-100, how many people are affected
    confidence_required: float = 70.0     # 0-100, how certain the client needs to be

    @property
    def complexity(self) -> float:
        """How hard this objective is to achieve (0-100)."""
        constraint_weight = min(len(self.constraints) * 8, 40)
        criteria_weight = min(len(self.success_criteria) * 6, 30)
        horizon_weight = min(self.time_horizon_years * 2, 20)
        scale_weight = self.population_scale * 0.1
        return min(100, constraint_weight + criteria_weight + horizon_weight + scale_weight)


@dataclass
class ObjectiveFraming:
    """One branched framing of the objective — varied constraints and weights."""

    framing_name: str
    constraint_priorities: dict[str, float]     # constraint -> weight 0-100
    criteria_weights: dict[str, float]          # criterion -> weight 0-100
    risk_adjustment: float                      # how risk tolerance was adjusted
    feasibility_score: float                    # 0-100, how achievable this framing is
    downstream_impact: float                    # 0-100, how much it would change outcomes
    score: float = 0.0
    outcome: str = ""


# --- Predefined objective templates ---

SAMPLE_OBJECTIVES: list[Objective] = [
    Objective(
        title="Secure Critical Infrastructure Against State-Level Adversary",
        domain=ObjectiveDomain.CYBERSECURITY,
        goal="Achieve zero successful intrusions against crown-jewel systems within 18 months",
        constraints=["No disruption to live services", "Budget capped at $50M",
                     "Must comply with NIST CSF 2.0", "No offensive operations"],
        success_criteria=["Mean time to detect < 15 min", "Crown jewel breach rate < 2%",
                          "100% asset coverage by Citadel", "Quarterly red-team pass rate > 90%"],
        risk_tolerance=RiskTolerance.AGGRESSIVE,
        time_horizon_years=1.5, population_scale=80, confidence_required=85,
    ),
    Objective(
        title="Diversify Supply Chain Away from Single-Source Dependency",
        domain=ObjectiveDomain.SUPPLY_CHAIN,
        goal="Reduce single-source dependency from 60% to below 15% within 36 months",
        constraints=["No cost increase > 8%", "Must maintain quality standards",
                     "No geopolitical exposure increase", "Existing supplier relationships preserved where possible"],
        success_criteria=["Single-source components < 15%", "Dual-source for 95% of critical path",
                          "Average lead time < 45 days", "Remnants survival score > 70 for all critical chains"],
        risk_tolerance=RiskTolerance.BALANCED,
        time_horizon_years=3, population_scale=60, confidence_required=75,
    ),
    Objective(
        title="Model Regional Conflict Impact on Operations",
        domain=ObjectiveDomain.NATIONAL_SECURITY,
        goal="Quantify operational risk across 10,000 conflict scenarios and identify continuity guarantees",
        constraints=["All scenarios must use real geographic data", "No classified information",
                     "Results must be actionable within 72 hours", "Must cover all 5 domains"],
        success_criteria=["10,000+ Kriegspiel scenarios generated", "Convergence rate > 60% on top outcomes",
                          "Remnants survival score for all critical institutions", "Awareness playbook for top 5 threats"],
        risk_tolerance=RiskTolerance.AGGRESSIVE,
        time_horizon_years=2, population_scale=90, confidence_required=80,
    ),
    Objective(
        title="Optimize Capital Allocation Across Portfolio",
        domain=ObjectiveDomain.CORPORATE_STRATEGY,
        goal="Maximize risk-adjusted returns across 8.2B population-scale market model",
        constraints=["No single position > 15% of portfolio", "ESG compliance required",
                     "Liquidity floor at 20%", "No leverage above 1.3x"],
        success_criteria=["Sharpe ratio > 1.5", "Max drawdown < 15%",
                          "Alpha Zero convergence > 70%", "Annual return > 12%"],
        risk_tolerance=RiskTolerance.BALANCED,
        time_horizon_years=5, population_scale=100, confidence_required=70,
    ),
    Objective(
        title="Energy Transition for Industrial Operations",
        domain=ObjectiveDomain.ENERGY_TRANSITION,
        goal="Transition 80% of industrial energy to renewables while maintaining output",
        constraints=["No production decrease > 5%", "Transition complete within 7 years",
                     "Cost premium < 12%", "Grid stability maintained"],
        success_criteria=["Renewable energy share > 80%", "Carbon emissions reduced > 60%",
                          "Energy cost per unit stable", "Zero unplanned outages from transition"],
        risk_tolerance=RiskTolerance.CONSERVATIVE,
        time_horizon_years=7, population_scale=70, confidence_required=80,
    ),
]


def simulate_framing(objective: Objective, seed: Optional[int] = None) -> dict:
    """Branch one framing of the objective. Per-branch function.

    Varies constraint priorities, criteria weights, and risk adjustment to
    see how the objective's definition shapes downstream feasibility.
    """
    rng = random.Random(seed or 42)

    # Vary constraint priorities
    constraint_priorities = {}
    for c in objective.constraints:
        base = rng.uniform(40, 100)
        constraint_priorities[c] = round(base, 1)

    # Vary criteria weights
    criteria_weights = {}
    for c in objective.success_criteria:
        base = rng.uniform(30, 100)
        criteria_weights[c] = round(base, 1)

    # Vary risk adjustment
    risk_map = {
        RiskTolerance.CONSERVATIVE: -10, RiskTolerance.BALANCED: 0, RiskTolerance.AGGRESSIVE: 15,
    }
    risk_adj = risk_map.get(objective.risk_tolerance, 0) + rng.uniform(-8, 8)

    # Feasibility: higher when constraints are fewer/lighter, criteria are achievable
    avg_constraint = (sum(constraint_priorities.values()) / len(constraint_priorities)
                      if constraint_priorities else 50)
    avg_criteria = (sum(criteria_weights.values()) / len(criteria_weights)
                    if criteria_weights else 50)
    complexity = objective.complexity
    feasibility = max(0, min(100,
        100 - complexity * 0.4 - avg_constraint * 0.2 + (100 - avg_criteria) * 0.1 + risk_adj * 0.3
        + rng.uniform(-10, 10)
    ))

    # Downstream impact: how much this framing would change the simulation outcomes
    impact = min(100, feasibility * 0.5 + abs(risk_adj) * 0.5 +
                 rng.uniform(10, 30))

    outcome = "high_feasibility" if feasibility > 65 else (
        "moderate" if feasibility > 40 else "low_feasibility"
    )
    score = feasibility * 0.6 + impact * 0.4

    return {
        "framing_name": f"Branch-{seed or 0}",
        "constraint_priorities": constraint_priorities,
        "criteria_weights": criteria_weights,
        "risk_adjustment": round(risk_adj, 1),
        "feasibility_score": round(feasibility, 1),
        "downstream_impact": round(impact, 1),
        "score": round(score, 2),
        "outcome": outcome,
    }


def generate_objective_scenarios(
    objective: Optional[Objective] = None,
    n_scenarios: int = 5000,
    seed: Optional[int] = None,
) -> dict:
    """Generate N branched framings of the objective and aggregate."""
    t0 = time.perf_counter()
    if objective is None:
        objective = SAMPLE_OBJECTIVES[0]

    raw = monte_carlo_branch(
        lambda s: simulate_framing(objective, s),
        n_scenarios,
        seed=seed,
    )

    high = sum(1 for r in raw if r["outcome"] == "high_feasibility")
    moderate = sum(1 for r in raw if r["outcome"] == "moderate")
    low = sum(1 for r in raw if r["outcome"] == "low_feasibility")

    avg_feasibility = sum(r["feasibility_score"] for r in raw) / len(raw) if raw else 0
    avg_impact = sum(r["downstream_impact"] for r in raw) / len(raw) if raw else 0
    convergence = convergence_rate(raw, outcome_key="outcome")
    best_raw = best_branch(raw, key="score")

    # Find the most influential constraint (highest average priority)
    constraint_avgs: dict[str, float] = {}
    for r in raw:
        for c, p in r["constraint_priorities"].items():
            constraint_avgs.setdefault(c, []).append(p)
    constraint_ranking = sorted(
        [(c, sum(v) / len(v)) for c, v in constraint_avgs.items()],
        key=lambda x: x[1], reverse=True,
    )

    return {
        "objective_title": objective.title,
        "objective_domain": objective.domain.value,
        "objective_complexity": round(objective.complexity, 1),
        "scenarios_run": len(raw),
        "high_feasibility": high,
        "moderate_feasibility": moderate,
        "low_feasibility": low,
        "avg_feasibility": round(avg_feasibility, 1),
        "avg_downstream_impact": round(avg_impact, 1),
        "convergence_rate": round(convergence, 4),
        "best_framing": {
            "feasibility": best_raw["feasibility_score"],
            "impact": best_raw["downstream_impact"],
            "risk_adjustment": best_raw["risk_adjustment"],
            "score": best_raw["score"],
        } if best_raw else None,
        "constraint_ranking": [{"constraint": c, "avg_priority": round(p, 1)} for c, p in constraint_ranking[:8]],
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
