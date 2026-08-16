"""Kriegspiel scenario generator — the 10,000-scenario engine.

This is the keystone. It takes a ``Battle`` seed and branches it into N
parallel scenarios using the shared ``monte_carlo_branch()`` primitive,
varying doctrine assignments, force compositions, and stochastic combat
outcomes. Returns an aggregated report showing which branch "won," the
convergence rate, and the distribution of outcomes.

Used by:
  - The gateway (feeds live scenario counts to index.html)
  - Citadel (runs the same engine inward on infrastructure)
  - Remnants (filters the final state for what survives)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate
from engines.kriegspiel.models import (
    Battle,
    Battlefield,
    BattleOutcome,
    BATTLEFIELDS,
    Doctrine,
    Force,
    Unit,
    UnitType,
)
from engines.kriegspiel.combat import simulate_battle
from engines.kriegspiel.geography import deploy_force


@dataclass
class ScenarioReport:
    """Aggregated report across all branched scenarios."""

    battlefield_name: str
    scenarios_run: int
    red_wins: int
    blue_wins: int
    stalemates: int
    decisive_battles: int
    convergence_rate: float           # fraction agreeing on the modal outcome
    avg_duration_hours: float
    avg_red_casualties: float
    avg_blue_casualties: float
    best_branch: Optional[BattleOutcome]
    branches: list[BattleOutcome] = field(default_factory=list)
    duration_ms: float = 0.0
    key_events: list[str] = field(default_factory=list)


def create_default_battle(battlefield: Optional[Battlefield] = None,
                          seed: Optional[int] = None) -> Battle:
    """Create a representative battle on the given (or random) battlefield."""
    rng = random.Random(seed)
    if battlefield is None:
        battlefield = rng.choice(BATTLEFIELDS)

    red_force = _create_force("Red Force", "red", rng)
    blue_force = _create_force("Blue Force", "blue", rng)
    deploy_force(red_force, battlefield, "red", seed)
    deploy_force(blue_force, battlefield, "blue", seed + 1 if seed else None)

    return Battle(
        battlefield=battlefield,
        red_force=red_force,
        blue_force=blue_force,
        objective="Secure strategic corridor",
        duration_hours=48,
        seed=seed,
    )


def _create_force(name: str, side: str, rng: random.Random) -> Force:
    """Generate a plausible force with varied units and a random doctrine."""
    doctrines = list(Doctrine)
    doctrine = rng.choice(doctrines)
    unit_mix = [
        (UnitType.INFANTRY, rng.randint(3, 6)),
        (UnitType.ARMOR, rng.randint(1, 3)),
        (UnitType.ARTILLERY, rng.randint(1, 2)),
        (UnitType.AIR, rng.randint(1, 2)),
        (UnitType.RECON, rng.randint(1, 2)),
        (UnitType.LOGISTICS, rng.randint(1, 2)),
    ]
    units = []
    for unit_type, count in unit_mix:
        for _ in range(count):
            units.append(Unit(
                unit_type=unit_type,
                strength=rng.uniform(70, 100),
                morale=rng.uniform(65, 95),
                supply=rng.uniform(75, 100),
                speed_kmh=rng.uniform(20, 50),
                engagement_range_km=rng.uniform(3, 15),
            ))
    return Force(name=name, doctrine=doctrine, units=units, side=side)


def generate_scenarios(
    battle: Optional[Battle] = None,
    n_scenarios: int = 10000,
    seed: Optional[int] = None,
) -> ScenarioReport:
    """Generate N branched battlefield scenarios and aggregate the results.

    This is the '10,000 battlefield scenarios in under a minute' function.
    """
    t0 = time.perf_counter()
    if battle is None:
        battle = create_default_battle(seed=seed)

    def _simulate_one(branch_seed: int) -> dict:
        varied_battle = _vary_battle(battle, branch_seed)
        outcome = simulate_battle(varied_battle, seed=branch_seed)
        return {
            "outcome": outcome.outcome,
            "score": outcome.score,
            "winner": outcome.winner,
            "red_casualties_pct": outcome.red_casualties_pct,
            "blue_casualties_pct": outcome.blue_casualties_pct,
            "duration_hours": outcome.duration_hours,
            "decisive": outcome.decisive,
            "key_event": outcome.key_event,
            "terrain_advantage": outcome.terrain_advantage,
        }

    raw_branches = monte_carlo_branch(_simulate_one, n_scenarios, seed=seed)

    branches = [BattleOutcome(
        winner=b["winner"],
        red_casualties_pct=b["red_casualties_pct"],
        blue_casualties_pct=b["blue_casualties_pct"],
        duration_hours=b["duration_hours"],
        decisive=b["decisive"],
        key_event=b["key_event"],
        terrain_advantage=b["terrain_advantage"],
        score=b["score"],
        outcome=b["outcome"],
    ) for b in raw_branches]

    red_wins = sum(1 for b in branches if b.winner == "red")
    blue_wins = sum(1 for b in branches if b.winner == "blue")
    stalemates = sum(1 for b in branches if b.winner == "stalemate")
    decisive = sum(1 for b in branches if b.decisive)

    convergence = convergence_rate(raw_branches, outcome_key="outcome")
    avg_duration = sum(b.duration_hours for b in branches) / len(branches) if branches else 0
    avg_red = sum(b.red_casualties_pct for b in branches) / len(branches) if branches else 0
    avg_blue = sum(b.blue_casualties_pct for b in branches) / len(branches) if branches else 0

    best_raw = best_branch(raw_branches, key="score")
    best = None
    if best_raw:
        best = BattleOutcome(
            winner=best_raw["winner"],
            red_casualties_pct=best_raw["red_casualties_pct"],
            blue_casualties_pct=best_raw["blue_casualties_pct"],
            duration_hours=best_raw["duration_hours"],
            decisive=best_raw["decisive"],
            key_event=best_raw["key_event"],
            terrain_advantage=best_raw["terrain_advantage"],
            score=best_raw["score"],
            outcome=best_raw["outcome"],
        )

    key_events = list(set(b.key_event for b in branches if b.key_event))[:10]

    return ScenarioReport(
        battlefield_name=battle.battlefield.name,
        scenarios_run=len(branches),
        red_wins=red_wins,
        blue_wins=blue_wins,
        stalemates=stalemates,
        decisive_battles=decisive,
        convergence_rate=round(convergence, 4),
        avg_duration_hours=round(avg_duration, 1),
        avg_red_casualties=round(avg_red, 1),
        avg_blue_casualties=round(avg_blue, 1),
        best_branch=best,
        branches=branches,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        key_events=key_events,
    )


def _vary_battle(battle: Battle, branch_seed: int) -> Battle:
    """Vary a battle's doctrine and unit stats for one branch."""
    rng = random.Random(branch_seed)
    doctrines = list(Doctrine)
    red_force = Force(
        name=battle.red_force.name,
        doctrine=rng.choice(doctrines),
        side="red",
        units=[Unit(
            unit_type=u.unit_type,
            strength=u.strength * rng.uniform(0.7, 1.3),
            morale=u.morale * rng.uniform(0.8, 1.2),
            supply=u.supply * rng.uniform(0.7, 1.3),
            position=u.position,
            speed_kmh=u.speed_kmh,
            engagement_range_km=u.engagement_range_km,
        ) for u in battle.red_force.units],
    )
    blue_force = Force(
        name=battle.blue_force.name,
        doctrine=rng.choice(doctrines),
        side="blue",
        units=[Unit(
            unit_type=u.unit_type,
            strength=u.strength * rng.uniform(0.7, 1.3),
            morale=u.morale * rng.uniform(0.8, 1.2),
            supply=u.supply * rng.uniform(0.7, 1.3),
            position=u.position,
            speed_kmh=u.speed_kmh,
            engagement_range_km=u.engagement_range_km,
        ) for u in battle.blue_force.units],
    )
    return Battle(
        battlefield=battle.battlefield,
        red_force=red_force,
        blue_force=blue_force,
        objective=battle.objective,
        duration_hours=battle.duration_hours,
        seed=branch_seed,
    )


def report_to_dict(report: ScenarioReport) -> dict:
    """Serialize a ScenarioReport to a JSON-friendly dict for the API."""
    return {
        "battlefield": report.battlefield_name,
        "scenarios_run": report.scenarios_run,
        "red_wins": report.red_wins,
        "blue_wins": report.blue_wins,
        "stalemates": report.stalemates,
        "decisive_battles": report.decisive_battles,
        "convergence_rate": report.convergence_rate,
        "avg_duration_hours": report.avg_duration_hours,
        "avg_red_casualties": report.avg_red_casualties,
        "avg_blue_casualties": report.avg_blue_casualties,
        "best_branch": {
            "winner": report.best_branch.winner,
            "score": report.best_branch.score,
            "key_event": report.best_branch.key_event,
            "duration_hours": report.best_branch.duration_hours,
            "red_casualties_pct": report.best_branch.red_casualties_pct,
            "blue_casualties_pct": report.best_branch.blue_casualties_pct,
        } if report.best_branch else None,
        "key_events": report.key_events,
        "duration_ms": report.duration_ms,
    }
