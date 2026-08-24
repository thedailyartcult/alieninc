"""Fidelity gate — Chronos' anti-placebo contract.

A historical battle may only branch into counterfactuals when the engine,
fed the real historical inputs, reproduces the recorded outcome across its
Monte Carlo branches within tolerance. The gate is computed from three
signals:

1. winner_fidelity  — fraction of branches predicting the actual victor
2. casualty fidelity — simulated casualty fractions vs the historical ones
3. convergence      — how decisive the branch distribution is

A battle passes only when winner_fidelity >= threshold AND mean simulated
casualty fractions are inside ``casualty_tolerance`` (relative) of history.
"""

from __future__ import annotations

from typing import Optional

from .engine import simulate_historical
from .models import HistoricalBattle
from .doctrines import resolve_doctrine

DEFAULT_WINNER_FIDELITY = 0.60
DEFAULT_CASUALTY_TOLERANCE = 0.55   # +/- 55% relative band on casualty fraction
ABSOLUTE_FLOOR = 0.035              # pp tolerance when actual fraction is tiny


def _ratio_close(simulated: Optional[float], actual: Optional[float],
                 tol: float) -> bool:
    """Hybrid tolerance: relative band, plus an absolute floor because a
    relative band is meaningless near zero (a battle with 1% recorded
    attacker losses cannot be judged on +/-55% of 1%)."""
    if actual is None or actual <= 0:
        return True
    if simulated is None:
        return False
    err = abs(simulated - actual)
    return err / actual <= tol or err <= ABSOLUTE_FLOOR


def fidelity_report(battle: HistoricalBattle, universes: int = 500,
                    seed: Optional[int] = None) -> dict:
    sim = simulate_historical(battle, universes=universes, seed=seed)
    actual_winner = battle.actual_winner

    winner_fidelity = sim["win_distribution"].get(actual_winner, 0.0)

    att_sim_frac = sim["avg_attacker_casualties"] / battle.attacker.strength \
        if battle.attacker.strength else None
    dfd_sim_frac = sim["avg_defender_casualties"] / battle.defender.strength \
        if battle.defender.strength else None

    attacker_cas_ok = _ratio_close(
        att_sim_frac, sim["actual_attacker_casualty_ratio"], DEFAULT_CASUALTY_TOLERANCE)
    defender_cas_ok = _ratio_close(
        dfd_sim_frac, sim["actual_defender_casualty_ratio"], DEFAULT_CASUALTY_TOLERANCE)

    checks = {
        "winner_reproduced": sim["predicted_winner"] == actual_winner,
        "winner_fidelity": round(winner_fidelity, 4),
        "attacker_casualties_in_band": attacker_cas_ok,
        "defender_casualties_in_band": defender_cas_ok,
    }
    passed = (
        checks["winner_reproduced"]
        and winner_fidelity >= DEFAULT_WINNER_FIDELITY
        and attacker_cas_ok
    )
    return {
        "battle_key": battle.battle_key,
        "name": battle.name,
        "year": battle.year,
        "actual_winner": actual_winner,
        "predicted_winner": sim["predicted_winner"],
        # Doctrinal attribution: each side's practiced method for this year.
        "doctrines": {
            "attacker": (lambda d: None if d.key == "generic-contemporary" else d.to_dict())(
                resolve_doctrine(battle.attacker.actors[0] if battle.attacker.actors else "",
                                 battle.year)),
            "defender": (lambda d: None if d.key == "generic-contemporary" else d.to_dict())(
                resolve_doctrine(battle.defender.actors[0] if battle.defender.actors else "",
                                 battle.year)),
        },
        "win_distribution": sim["win_distribution"],
        "convergence": sim["convergence"],
        "simulated_attacker_casualty_fraction": round(att_sim_frac, 4) if att_sim_frac else None,
        "actual_attacker_casualty_fraction": round(sim["actual_attacker_casualty_ratio"], 4)
            if sim["actual_attacker_casualty_ratio"] else None,
        "simulated_defender_casualty_fraction": round(dfd_sim_frac, 4) if dfd_sim_frac else None,
        "actual_defender_casualty_fraction": round(sim["actual_defender_casualty_ratio"], 4)
            if sim["actual_defender_casualty_ratio"] else None,
        "checks": checks,
        "fidelity_score": round(winner_fidelity * (1.0 if attacker_cas_ok else 0.7), 4),
        "passed": bool(passed),
        "gate_thresholds": {
            "winner_fidelity_min": DEFAULT_WINNER_FIDELITY,
            "casualty_tolerance_rel": DEFAULT_CASUALTY_TOLERANCE,
        },
    }


def assert_gate(report: dict) -> None:
    """Raise unless the fidelity report passes. Callers use this to block what-if."""
    if not report.get("passed"):
        failed = [k for k, ok in report.get("checks", {}).items() if not ok]
        raise PermissionError(
            f"Fidelity gate FAILED for {report.get('battle_key')}: {failed}. "
            f"Counterfactual branches are blocked until the engine reproduces "
            f"this battle's recorded outcome."
        )
