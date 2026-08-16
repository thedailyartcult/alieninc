"""Remnants continuity analysis — what survives a conflict.

Takes Kriegspiel battle outcomes (or any conflict scenario) and models which
institutions, doctrines, supply chains, and cultural artifacts outlast the
destruction. Each "survivor" is scored by:

  - **Resilience**: how well it absorbs shock without collapsing
  - **Adaptability**: how quickly it reconfigures under new conditions
  - **Continuity**: how much of its core function survives the transition
  - **Dependency health**: whether the things it depends on also survived

The output is a ranked list of survivors with their continuity scores — the
institutions and supply chains that will still be standing after the dust
settles.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate


class SurvivorType(str, Enum):
    """What kind of thing survives (or doesn't)."""

    INSTITUTION = "institution"          # government, courts, banks
    DOCTRINE = "doctrine"                # military/strategic doctrine
    SUPPLY_CHAIN = "supply_chain"        # logistics, manufacturing
    CULTURAL = "cultural"                # language, religion, art, identity
    INFRASTRUCTURE = "infrastructure"    # power, water, comms, roads
    KNOWLEDGE = "knowledge"              # education, research, records
    ECONOMIC = "economic"                # currency, trade networks, markets


@dataclass
class Survivor:
    """An institution, doctrine, or supply chain that might outlast a conflict."""

    name: str
    survivor_type: SurvivorType
    resilience: float = 50.0          # 0-100, absorbs shock without collapsing
    adaptability: float = 50.0        # 0-100, reconfigures under new conditions
    continuity: float = 50.0          # 0-100, core function survives transition
    dependency_strength: float = 50.0 # 0-100, how dependent on other survivors
    population_reach: float = 50.0    # 0-100, how many people it serves
    age_years: float = 50.0           # how long it's existed (older = more entrenched)

    @property
    def survival_score(self) -> float:
        """Base survival score before conflict conditions are applied."""
        entrenchment = min(self.age_years / 100, 1.0) * 20
        independence = (100 - self.dependency_strength) / 100 * 15
        return (self.resilience * 0.30 + self.adaptability * 0.25 +
                self.continuity * 0.20 + independence + entrenchment +
                self.population_reach / 100 * 10)


@dataclass
class ConflictCondition:
    """The conditions produced by a Kriegspiel battle outcome."""

    intensity: float = 50.0           # 0-100, how destructive the conflict was
    duration_months: float = 12.0     # how long the conflict lasted
    infrastructure_damage: float = 50.0  # 0-100
    population_displacement: float = 30.0  # 0-100
    supply_disruption: float = 50.0   # 0-100
    cultural_destruction: float = 20.0  # 0-100


@dataclass
class SurvivalOutcome:
    """The result of one branched survival scenario."""

    survivor_name: str
    survived: bool
    final_score: float                # 0-100, how well it survived
    damage_taken: float               # 0-100, how much it was degraded
    recovery_time_months: float       # how long to recover core function
    key_factor: str                   # what determined survival or collapse
    score: float = 0.0                # for best_branch()
    outcome: str = ""                 # "survived" or "collapsed" for convergence


@dataclass
class RemnantsReport:
    """Aggregated report across all branched survival scenarios."""

    conflict_intensity: float
    scenarios_run: int
    survivors: list[SurvivalOutcome]
    survival_rate: float              # fraction that survived across all branches
    most_resilient: list[tuple[str, float]]  # (name, avg_score)
    most_fragile: list[tuple[str, float]]    # (name, avg_score)
    avg_recovery_time: float
    convergence_rate: float
    best_survivor: Optional[SurvivalOutcome]
    duration_ms: float = 0.0


# --- Predefined survivor populations (real-world institutions/doctrines) ---

SAMPLE_SURVIVORS: list[Survivor] = [
    Survivor("Central Bank", SurvivorType.INSTITUTION, resilience=80, adaptability=60,
             continuity=85, dependency_strength=40, population_reach=90, age_years=100),
    Survivor("Civil Courts", SurvivorType.INSTITUTION, resilience=70, adaptability=50,
             continuity=80, dependency_strength=30, population_reach=80, age_years=150),
    Survivor("Armed Forces Doctrine", SurvivorType.DOCTRINE, resilience=60, adaptability=75,
             continuity=65, dependency_strength=50, population_reach=40, age_years=80),
    Survivor("Food Supply Chain", SurvivorType.SUPPLY_CHAIN, resilience=65, adaptability=80,
             continuity=90, dependency_strength=60, population_reach=100, age_years=200),
    Survivor("Energy Grid", SurvivorType.INFRASTRUCTURE, resilience=45, adaptability=35,
             continuity=70, dependency_strength=70, population_reach=95, age_years=60),
    Survivor("Telecom Network", SurvivorType.INFRASTRUCTURE, resilience=40, adaptability=60,
             continuity=55, dependency_strength=65, population_reach=90, age_years=40),
    Survivor("National Language", SurvivorType.CULTURAL, resilience=95, adaptability=90,
             continuity=99, dependency_strength=10, population_reach=100, age_years=500),
    Survivor("Religious Institution", SurvivorType.CULTURAL, resilience=90, adaptability=70,
             continuity=95, dependency_strength=15, population_reach=85, age_years=300),
    Survivor("University System", SurvivorType.KNOWLEDGE, resilience=55, adaptability=65,
             continuity=75, dependency_strength=55, population_reach=50, age_years=120),
    Survivor("Medical Records", SurvivorType.KNOWLEDGE, resilience=50, adaptability=40,
             continuity=60, dependency_strength=60, population_reach=70, age_years=30),
    Survivor("Currency", SurvivorType.ECONOMIC, resilience=35, adaptability=45,
             continuity=50, dependency_strength=80, population_reach=95, age_years=80),
    Survivor("Trade Routes", SurvivorType.ECONOMIC, resilience=60, adaptability=85,
             continuity=70, dependency_strength=50, population_reach=75, age_years=100),
    Survivor("Water Utility", SurvivorType.INFRASTRUCTURE, resilience=70, adaptability=30,
             continuity=85, dependency_strength=75, population_reach=100, age_years=100),
    Survivor("Artistic Tradition", SurvivorType.CULTURAL, resilience=85, adaptability=95,
             continuity=90, dependency_strength=5, population_reach=60, age_years=400),
]


def simulate_survival(
    survivor: Survivor,
    condition: ConflictCondition,
    seed: Optional[int] = None,
) -> dict:
    """Simulate whether one survivor outlasts the conflict. Per-branch function."""
    rng = random.Random(seed or 42)

    base = survivor.survival_score
    # Conflict conditions erode the survival score
    damage = (condition.intensity * 0.25
              + condition.infrastructure_damage * 0.20
              + condition.supply_disruption * 0.20
              + condition.population_displacement * 0.15
              + condition.cultural_destruction * 0.20)
    # Longer conflicts are worse, but adaptation helps over time
    duration_penalty = min(condition.duration_months / 60, 1.0) * 15
    adaptation_bonus = (survivor.adaptability / 100) * min(condition.duration_months / 24, 1.0) * 10

    # Stochastic variation
    luck = rng.uniform(-15, 15)
    final = base - damage - duration_penalty + adaptation_bonus + luck
    final = max(0, min(100, final))

    survived = final > 40
    damage_taken = 100 - final
    recovery_time = max(0, (100 - final) * (1 - survivor.adaptability / 100) * 0.5) if survived else 999

    factors = {
        "resilience": survivor.resilience,
        "adaptability": survivor.adaptability,
        "continuity": survivor.continuity,
        "entrenchment": min(survivor.age_years / 100, 1.0) * 100,
        "independence": 100 - survivor.dependency_strength,
    }
    key_factor = max(factors, key=factors.get) if survived else min(factors, key=factors.get)

    return {
        "survivor_name": survivor.name,
        "survived": survived,
        "final_score": round(final, 1),
        "damage_taken": round(damage_taken, 1),
        "recovery_time_months": round(recovery_time, 1),
        "key_factor": key_factor,
        "score": round(final, 2),
        "outcome": "survived" if survived else "collapsed",
    }


def generate_continuity_scenarios(
    survivors: Optional[list[Survivor]] = None,
    condition: Optional[ConflictCondition] = None,
    n_scenarios: int = 5000,
    seed: Optional[int] = None,
) -> RemnantsReport:
    """Generate N branched survival scenarios and aggregate the results."""
    t0 = time.perf_counter()
    if survivors is None:
        survivors = SAMPLE_SURVIVORS
    if condition is None:
        condition = ConflictCondition()

    all_outcomes: list[SurvivalOutcome] = []
    all_raw: list[dict] = []
    survivor_scores: dict[str, list[float]] = {}

    for survivor in survivors:
        raw = monte_carlo_branch(
            lambda s: simulate_survival(survivor, condition, s),
            max(1, n_scenarios // len(survivors)),
            seed=seed,
        )
        all_raw.extend(raw)
        for r in raw:
            all_outcomes.append(SurvivalOutcome(
                survivor_name=r["survivor_name"],
                survived=r["survived"],
                final_score=r["final_score"],
                damage_taken=r["damage_taken"],
                recovery_time_months=r["recovery_time_months"],
                key_factor=r["key_factor"],
                score=r["score"],
                outcome=r["outcome"],
            ))
            survivor_scores.setdefault(r["survivor_name"], []).append(r["final_score"])

    survived_count = sum(1 for o in all_outcomes if o.survived)
    survival_rate = survived_count / len(all_outcomes) if all_outcomes else 0

    avg_scores = {name: sum(scores) / len(scores) for name, scores in survivor_scores.items()}
    most_resilient = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)[:5]
    most_fragile = sorted(avg_scores.items(), key=lambda x: x[1])[:5]

    avg_recovery = sum(o.recovery_time_months for o in all_outcomes if o.survived) / max(1, survived_count)
    convergence = convergence_rate(all_raw, outcome_key="outcome")
    best_raw = best_branch(all_raw, key="score")
    best = SurvivalOutcome(
        survivor_name=best_raw["survivor_name"], survived=best_raw["survived"],
        final_score=best_raw["final_score"], damage_taken=best_raw["damage_taken"],
        recovery_time_months=best_raw["recovery_time_months"],
        key_factor=best_raw["key_factor"], score=best_raw["score"],
        outcome=best_raw["outcome"],
    ) if best_raw else None

    return RemnantsReport(
        conflict_intensity=condition.intensity,
        scenarios_run=len(all_outcomes),
        survivors=all_outcomes,
        survival_rate=round(survival_rate, 4),
        most_resilient=most_resilient,
        most_fragile=most_fragile,
        avg_recovery_time=round(avg_recovery, 1),
        convergence_rate=round(convergence, 4),
        best_survivor=best,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


def report_to_dict(report: RemnantsReport) -> dict:
    """Serialize a RemnantsReport to a JSON-friendly dict."""
    return {
        "conflict_intensity": report.conflict_intensity,
        "scenarios_run": report.scenarios_run,
        "survival_rate": report.survival_rate,
        "survived_count": sum(1 for s in report.survivors if s.survived),
        "collapsed_count": sum(1 for s in report.survivors if not s.survived),
        "most_resilient": [{"name": n, "avg_score": round(s, 1)} for n, s in report.most_resilient],
        "most_fragile": [{"name": n, "avg_score": round(s, 1)} for n, s in report.most_fragile],
        "avg_recovery_time": report.avg_recovery_time,
        "convergence_rate": report.convergence_rate,
        "best_survivor": {
            "name": report.best_survivor.survivor_name,
            "final_score": report.best_survivor.final_score,
            "key_factor": report.best_survivor.key_factor,
            "recovery_time": report.best_survivor.recovery_time_months,
        } if report.best_survivor else None,
        "duration_ms": report.duration_ms,
    }
