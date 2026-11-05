"""Awareness response simulation — Monte Carlo incident response branching.

Takes a threat event and a candidate playbook, then branches the response
across N parallel scenarios. Each branch varies execution speed, action
success rates, threat spread dynamics, and collateral effects. The aggregated
report shows which playbook contains the threat fastest, mitigates the most
damage, and preserves the most operational continuity.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from sims_core.monte_carlo import monte_carlo_branch, best_branch, convergence_rate
from engines.awareness.models import (
    IncidentResponse,
    Playbook,
    ResponseAction,
    ResponseOutcome,
    SAMPLE_PLAYBOOKS,
    SAMPLE_THREATS,
    ThreatEvent,
    ThreatType,
)


@dataclass
class PlaybookEvaluation:
    """Aggregated results for one playbook across all branches."""

    playbook_name: str
    threat_name: str
    scenarios_run: int
    contained: int
    partially_contained: int
    failed: int
    exacerbated: int
    avg_containment_time: float
    avg_damage_mitigated: float
    avg_collateral: float
    avg_continuity: float
    success_rate: float
    best_branch: Optional[IncidentResponse]


@dataclass
class AwarenessReport:
    """Full report across all playbook evaluations for a threat."""

    threat_name: str
    threat_type: str
    threat_severity: str
    scenarios_run: int
    evaluations: list[PlaybookEvaluation]
    best_playbook: Optional[PlaybookEvaluation]
    convergence_rate: float
    duration_ms: float = 0.0


def simulate_response(
    threat: ThreatEvent,
    playbook: Playbook,
    seed: Optional[int] = None,
    population_reach: float = 1.0,
) -> dict:
    """Simulate one incident response branch. Per-branch function.

    Models the race between threat spread and response execution. Each action
    in the playbook has a stochastic success chance. The threat keeps spreading
    while the response executes. Outcome depends on whether the response
    outpaces the threat.

    ``population_reach`` (0.0-1.0, default 1.0 = no penalty) is the affected
    population's reachability — how well response actions (notifications,
    coordination, guidance) land. A low-fluency / low-trust population is
    harder to reach, so response actions succeed less often *inside the engine*
    (not just a post-hoc report adjustment).
    """
    rng = random.Random(seed or 42)
    population_reach = max(0.3, min(1.0, population_reach))

    # Threat dynamics — how fast it spreads and how hard it persists
    threat_spread_per_min = (threat.spread_rate / 100) * rng.uniform(0.5, 2.0)
    threat_persistence = (threat.persistence / 100) * rng.uniform(0.7, 1.3)

    # Response dynamics — how fast the playbook executes
    actions = playbook.actions
    action_speed = (playbook.speed / 100) * rng.uniform(0.6, 1.4)
    minutes_per_action = max(0.5, 10 / max(action_speed, 0.1))

    # Simulate the response execution tick by tick
    damage_accumulated = 0.0
    actions_executed = 0
    threat_contained = False
    containment_time = 0.0

    for i, action in enumerate(actions):
        # Each tick, the threat spreads
        tick_time = minutes_per_action
        containment_time += tick_time
        damage_accumulated += threat_spread_per_min * tick_time * (1 - i * 0.1)

        # Action success chance — depends on automation, coverage, reachability,
        # and threat persistence. A hard-to-reach population lowers success.
        base_success = (playbook.coverage / 100) * (playbook.automation_level / 100)
        persistence_resistance = threat_persistence * 0.3
        action_success = max(0.1, base_success * population_reach
                             - persistence_resistance + rng.uniform(-0.2, 0.2))

        if rng.random() < action_success:
            actions_executed += 1
            # Each successful action reduces the threat spread
            threat_spread_per_min *= 0.6
            if threat_spread_per_min < 0.5:
                threat_contained = True
                break
        # Failed actions don't reduce spread but cost time

    # Calculate outcomes
    max_damage = 100.0
    damage_pct = min(damage_accumulated, max_damage)
    damage_mitigated = max(0, 100 - damage_pct)

    collateral = (playbook.collateral_risk / 100) * rng.uniform(0.5, 1.5) * (actions_executed / max(len(actions), 1))
    collateral = min(collateral, 100)

    # Operational continuity = 100 - damage - collateral
    continuity = max(0, 100 - damage_pct * 0.6 - collateral * 0.4)

    # Determine outcome
    if threat_contained and damage_mitigated > 70:
        outcome = ResponseOutcome.CONTAINED
    elif threat_contained and damage_mitigated > 40:
        outcome = ResponseOutcome.PARTIALLY_CONTAINED
    elif damage_mitigated < 20 and collateral > 30:
        outcome = ResponseOutcome.EXACERBATED
    else:
        outcome = ResponseOutcome.FAILED

    score = (damage_mitigated * 0.35 + continuity * 0.30
             + (100 - collateral) * 0.15
             + (100 - containment_time) * 0.10
             + (50 if outcome == ResponseOutcome.CONTAINED else 0))

    return {
        "playbook_name": playbook.name,
        "threat_name": threat.name,
        "outcome": outcome.value,
        "containment_time_min": round(containment_time, 1),
        "damage_mitigated_pct": round(damage_mitigated, 1),
        "collateral_damage_pct": round(collateral, 1),
        "operational_continuity": round(continuity, 1),
        "actions_executed": actions_executed,
        "score": round(score, 2),
        "outcome_label": outcome.value,
        "population_reach": round(population_reach, 3),
    }


def generate_response_scenarios(
    threat: Optional[ThreatEvent] = None,
    playbooks: Optional[list[Playbook]] = None,
    n_scenarios: int = 5000,
    seed: Optional[int] = None,
    population_reach: float = 1.0,
) -> AwarenessReport:
    """Evaluate all candidate playbooks against a threat via Monte Carlo branching.

    ``population_reach`` (0.0-1.0, default 1.0) scales how well response actions
    land — derived from the affected population's digital-fluency / trust /
    connectivity profile. Applied *inside* each branch so a hard-to-reach
    population lowers response success in the engine itself.
    """
    t0 = time.perf_counter()
    if threat is None:
        threat = SAMPLE_THREATS[0]
    if playbooks is None:
        # Select playbooks that target this threat type, or fall back to all
        matching = [p for p in SAMPLE_PLAYBOOKS if p.target_threat_type == threat.threat_type]
        playbooks = matching if matching else SAMPLE_PLAYBOOKS[:4]

    all_raw: list[dict] = []
    evaluations: list[PlaybookEvaluation] = []

    scenarios_per_pb = max(1, n_scenarios // len(playbooks))

    for pb in playbooks:
        raw = monte_carlo_branch(
            lambda s: simulate_response(threat, pb, s, population_reach=population_reach),
            scenarios_per_pb,
            seed=seed,
        )
        all_raw.extend(raw)

        contained = sum(1 for r in raw if r["outcome"] == "contained")
        partial = sum(1 for r in raw if r["outcome"] == "partially_contained")
        failed = sum(1 for r in raw if r["outcome"] == "failed")
        exacerbated = sum(1 for r in raw if r["outcome"] == "exacerbated")

        avg_time = sum(r["containment_time_min"] for r in raw) / len(raw) if raw else 0
        avg_mitigated = sum(r["damage_mitigated_pct"] for r in raw) / len(raw) if raw else 0
        avg_collateral = sum(r["collateral_damage_pct"] for r in raw) / len(raw) if raw else 0
        avg_continuity = sum(r["operational_continuity"] for r in raw) / len(raw) if raw else 0
        success_rate = (contained + partial) / len(raw) if raw else 0

        best_raw = best_branch(raw, key="score")
        best_ir = IncidentResponse(
            playbook_name=best_raw["playbook_name"], threat_name=best_raw["threat_name"],
            outcome=ResponseOutcome(best_raw["outcome"]),
            containment_time_min=best_raw["containment_time_min"],
            damage_mitigated_pct=best_raw["damage_mitigated_pct"],
            collateral_damage_pct=best_raw["collateral_damage_pct"],
            operational_continuity=best_raw["operational_continuity"],
            actions_executed=best_raw["actions_executed"],
            score=best_raw["score"], outcome_label=best_raw["outcome_label"],
        ) if best_raw else None

        evaluations.append(PlaybookEvaluation(
            playbook_name=pb.name, threat_name=threat.name,
            scenarios_run=len(raw), contained=contained, partially_contained=partial,
            failed=failed, exacerbated=exacerbated,
            avg_containment_time=round(avg_time, 1),
            avg_damage_mitigated=round(avg_mitigated, 1),
            avg_collateral=round(avg_collateral, 1),
            avg_continuity=round(avg_continuity, 1),
            success_rate=round(success_rate, 4),
            best_branch=best_ir,
        ))

    convergence = convergence_rate(all_raw, outcome_key="outcome")
    best_eval = max(evaluations, key=lambda e: e.success_rate) if evaluations else None

    return AwarenessReport(
        threat_name=threat.name,
        threat_type=threat.threat_type.value,
        threat_severity=threat.severity.value,
        scenarios_run=len(all_raw),
        evaluations=evaluations,
        best_playbook=best_eval,
        convergence_rate=round(convergence, 4),
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


def report_to_dict(report: AwarenessReport) -> dict:
    """Serialize an AwarenessReport to a JSON-friendly dict."""
    return {
        "threat_name": report.threat_name,
        "threat_type": report.threat_type,
        "threat_severity": report.threat_severity,
        "scenarios_run": report.scenarios_run,
        "convergence_rate": report.convergence_rate,
        "duration_ms": report.duration_ms,
        "best_playbook": {
            "name": report.best_playbook.playbook_name,
            "success_rate": report.best_playbook.success_rate,
            "contained": report.best_playbook.contained,
            "avg_containment_time": report.best_playbook.avg_containment_time,
            "avg_damage_mitigated": report.best_playbook.avg_damage_mitigated,
            "avg_continuity": report.best_playbook.avg_continuity,
        } if report.best_playbook else None,
        "evaluations": [
            {
                "playbook": ev.playbook_name,
                "scenarios": ev.scenarios_run,
                "contained": ev.contained,
                "partial": ev.partially_contained,
                "failed": ev.failed,
                "exacerbated": ev.exacerbated,
                "success_rate": ev.success_rate,
                "avg_containment_time": ev.avg_containment_time,
                "avg_damage_mitigated": ev.avg_damage_mitigated,
                "avg_collateral": ev.avg_collateral,
                "avg_continuity": ev.avg_continuity,
            }
            for ev in report.evaluations
        ],
    }
