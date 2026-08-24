"""Chronos combat engine — historical battle resolution.

Physics: aimed-fire Lanchester square law over time ticks, with combat power
derived from verified strengths × quality multipliers (CDB90 ratings) ×
equipment ratios weighted by the era profile. Stochastic per-branch noise
enables Monte Carlo branching via ``sims_core.monte_carlo.monte_carlo_branch``.

Calibration contract: with historical inputs the engine must reproduce the
recorded victor before counterfactual branches are permitted (see fidelity.py).
"""

from __future__ import annotations

import math
import random
from typing import Optional

try:
    from sims_core.monte_carlo import monte_carlo_branch, convergence_rate
except ImportError:  # pragma: no cover - direct import fallback when suite root on path
    from sims_core.monte_carlo import monte_carlo_branch, convergence_rate

from .models import ChronosOutcome, EraProfile, HistoricalBattle, HistoricalSide
from .doctrines import (
    DoctrineProfile,
    attacker_power_mult,
    defender_power_mult,
    resolve_doctrine,
)

TICK_HOURS = 6.0
ROUT_FRACTION = 0.72          # force breaks when fighting strength falls to 72%
STALEMATE_MARGIN = 1.08       # within 8% relative power at end = stalemate
DECISIVE_RATIO = 1.6
EXCHANGE_SCALE = 5.0          # calibrated vs CDB90 corpus (see calibrate.py)
ATTACK_INITIATIVE = 1.6      # local force concentration at the point of attack
FRICTION_DEFENSE_BIAS = 0.10
BASELINE_ATTRITION = 0.35
POWER_FEEDBACK = 1.2          # suppressive-fire coupling exponent
CONTACT_RAMP_TICKS = 2.0      # approach-phase ticks before full firepower
BREAK_OFF_FRACTION = 0.94     # attacker breaks off once ~6% of power is gone
BREAK_OFF_MARGIN = 1.02       # and the defense is demonstrably holding

# Terrain defense bonuses (multiplicative on defender power), keyed by
# canonical CDB90 labels written by chronos_sync.
TERRAIN_DEFENSE = {
    "flat": 1.0,
    "rolling": 1.08,
    "rugged": 1.32,
    "bare": 1.0,
    "mixed": 1.02,
    "desert": 1.04,
    "wooded": 1.18,
    "marsh": 1.25,
    "urban": 1.42,
    "dunes": 1.05,
}

WEATHER_EFFECT = {
    "dry": 1.0,
    "wet": 0.93,
}


def _terrain_defense(terrain: str) -> float:
    bonus = 1.0
    for token in (terrain or "").split(","):
        bonus *= TERRAIN_DEFENSE.get(token.strip().lower(), 1.0)
    return bonus


def side_combat_power(
    side: HistoricalSide,
    era: EraProfile,
    terrain: str,
    weather: str,
    jitter_rng: Optional[random.Random] = None,
    air_superiority: int = 0,
    doctrine: Optional[DoctrineProfile] = None,
    duration_hours: float = 24.0,
) -> float:
    strength = max(side.strength, 1.0)
    quality = side.quality_multiplier()
    equipment = side.equipment_multiplier(era)
    posture = 1.0 + 0.12 * era.air_effectiveness if side.is_attacker else _terrain_defense(terrain)
    surprise = 1.0 + 0.05 * (side.surprise or 0.0)
    wx = WEATHER_EFFECT.get((weather or "").split(",")[0].strip().lower(), 1.0)
    initiative = ATTACK_INITIATIVE if side.is_attacker else 1.0
    air_shift = 1.0
    holds_air = (air_superiority > 0) == side.is_attacker and air_superiority != 0
    if air_superiority:
        air_shift = (1.0 + 0.22 * era.air_effectiveness) if holds_air \
            else max(1.0 - 0.15 * era.air_effectiveness, 0.7)
    # Doctrine: the army's practiced method in that year (cited registry).
    if doctrine is not None and not _GENERIC_DOCTRINE(doctrine):
        if side.is_attacker:
            doctrine_shift = attacker_power_mult(doctrine, terrain, duration_hours)
        else:
            doctrine_shift = defender_power_mult(doctrine)
    else:
        doctrine_shift = 1.0
    power = strength * quality * equipment * posture * surprise * wx * initiative * air_shift * doctrine_shift
    if jitter_rng is not None:
        # Fog of war: intelligence error on either side's effective strength.
        power *= jitter_rng.uniform(0.82, 1.18)
    return power


def _GENERIC_DOCTRINE(doc: DoctrineProfile) -> bool:
    return doc.key == "generic-contemporary"


def _casualty_exchange(
    att_power: float,
    dfd_power: float,
    ticks: int,
    era: EraProfile,
    rng: random.Random,
    attacker_surprise: float = 0.0,
    defender_flexibility: float = 1.0,
    attacker_flexibility: float = 1.0,
) -> tuple[float, float]:
    """Ratio-driven mutual exchange calibrated to the CDB90 corpus.

    Each side's fractional loss rate scales with the opponent-to-own
    strength ratio raised to ``POWER_FEEDBACK`` — a self-reinforcing
    dynamic where a weakening force both deals and receives less fire.
    Outcome asymmetry (attacks succeed ~70% historically even at numeric
    parity) is encoded once via ATTACK_INITIATIVE inside combat power.
    """
    a_strength = att_power
    d_strength = dfd_power
    k = EXCHANGE_SCALE * era.attrition_rate * TICK_HOURS / 24.0
    baseline_daily = era.attrition_rate * BASELINE_ATTRITION
    # Surprise: a surprised defender coordinates slowly, so the attack's
    # opening phase lands before the defense's firepower matures. Doctrinal
    # flexibility modulates this both ways: an inflexible defender (low
    # flexibility) is slow to react (longer ramp); a flexible attacker
    # recovers faster from being caught off guard itself.
    surprise = max(attacker_surprise, 0.0) / max(attacker_flexibility, 0.5)
    reaction = 1.0 / max(defender_flexibility, 0.5)
    surprise_ticks = CONTACT_RAMP_TICKS * (1.0 + 0.75 * surprise) * min(reaction, 1.6)
    for tick_i in range(ticks):
        # Break-off FIRST (decision precedes the day's fighting): a failing
        # attack disengages before annihilation. Corpus ground truth (WWII):
        # failed attacks cost attackers ~5.7% on average — barely more than
        # successful ones — because commanders cut their losses once the
        # defense is clearly holding.
        if (tick_i >= 1
                and a_strength < att_power * BREAK_OFF_FRACTION
                and d_strength > a_strength * BREAK_OFF_MARGIN):
            a_strength -= (att_power - a_strength) * rng.uniform(0.1, 0.25)
            break
        # Approach phase: the opening hours see skirmish-level contact while
        # attacks deploy; full firepower develops over roughly a day.
        ramp = min((tick_i + 1) / max(surprise_ticks, 0.5), 1.0)
        ratio = max(d_strength / max(a_strength, 1e-9), 1e-6)
        a_loss_frac = min(k * ramp * rng.uniform(0.75, 1.25) * ratio ** POWER_FEEDBACK
                          * era.attacker_casualty_scale, 0.2)
        d_loss_frac = min(k * ramp * rng.uniform(0.75, 1.25) * ratio ** (-POWER_FEEDBACK)
                          * era.defender_casualty_scale, 0.25)
        a_strength *= (1.0 - a_loss_frac)
        d_strength *= (1.0 - d_loss_frac)
        a_strength -= att_power * baseline_daily * TICK_HOURS / 24.0 * rng.uniform(0.4, 1.0) * ramp \
            * era.attacker_casualty_scale
        d_strength -= dfd_power * baseline_daily * TICK_HOURS / 24.0 * rng.uniform(0.4, 1.0) * ramp \
            * era.defender_casualty_scale
        if d_strength < dfd_power * ROUT_FRACTION:
            d_collapse = dfd_power * ROUT_FRACTION - d_strength
            d_strength -= d_collapse * rng.uniform(0.5, 1.1)
            break
        if a_strength < att_power * ROUT_FRACTION:
            a_collapse = att_power * ROUT_FRACTION - a_strength
            a_strength -= a_collapse * rng.uniform(0.5, 1.1)
            break
    return att_power - a_strength, dfd_power - d_strength


def resolve_battle(battle: HistoricalBattle, seed: int,
                   overrides: Optional[dict] = None) -> ChronosOutcome:
    """Resolve one branch of a historical battle.

    ``overrides`` enables what-if branches: {"attacker_strength_mult": x},
    {"defender_quality_add": y}, {"weather": "..."}, etc. Exactly one override
    per what-if run is the intended usage.
    """
    overrides = overrides or {}
    rng = random.Random(seed)
    era = battle.era

    attacker = battle.attacker
    defender = battle.defender

    # Doctrines: each side's practiced method for this year. What-if may
    # swap either side's doctrine via {"attacker_doctrine": "Germany"} /
    # {"defender_doctrine": "USSR"} - a counterfactual lever in its own right.
    att_doc = resolve_doctrine(
        overrides.get("attacker_doctrine") or (attacker.actors[0] if attacker.actors else ""),
        battle.year,
    )
    dfd_doc = resolve_doctrine(
        overrides.get("defender_doctrine") or (defender.actors[0] if defender.actors else ""),
        battle.year,
    )

    att_power = side_combat_power(attacker, era, battle.terrain, battle.weather, rng,
                                  air_superiority=battle.air_superiority,
                                  doctrine=att_doc, duration_hours=battle.duration_hours)
    dfd_power = side_combat_power(defender, era, battle.terrain, battle.weather, rng,
                                  air_superiority=battle.air_superiority,
                                  doctrine=dfd_doc, duration_hours=battle.duration_hours)

    att_mult = overrides.get("attacker_strength_mult", 1.0)
    dfd_mult = overrides.get("defender_strength_mult", 1.0)
    att_power *= att_mult
    dfd_power *= dfd_mult
    if "defender_quality_add" in overrides:
        q = defender.quality_multiplier()
        dfd_power *= (q + overrides["defender_quality_add"]) / max(q, 1e-6)
    if "attacker_quality_add" in overrides:
        q = attacker.quality_multiplier()
        att_power *= (q + overrides["attacker_quality_add"]) / max(q, 1e-6)
    if "terrain" in overrides:
        base_dfd = side_combat_power(defender, era, battle.terrain, battle.weather)
        new_dfd = side_combat_power(defender, era, overrides["terrain"], battle.weather)
        dfd_power *= new_dfd / max(base_dfd, 1e-6)

    duration = max(battle.duration_hours, TICK_HOURS)
    ticks = max(int(math.ceil(duration / TICK_HOURS)), 1)

    att_cas_power, dfd_cas_power = _casualty_exchange(
        att_power, dfd_power, ticks, era, rng,
        attacker_surprise=float(attacker.surprise or 0.0),
        defender_flexibility=dfd_doc.flexibility,
        attacker_flexibility=att_doc.flexibility,
    )

    att_frac = att_cas_power / max(att_power, 1e-6)
    dfd_frac = dfd_cas_power / max(dfd_power, 1e-6)

    att_remaining = 1.0 - att_frac
    dfd_remaining = 1.0 - dfd_frac

    key_event = ""
    decisive = False
    if dfd_remaining < ROUT_FRACTION <= att_remaining:
        winner = "attacker"
        key_event = "defense collapsed"
    elif att_remaining < ROUT_FRACTION <= dfd_remaining:
        winner = "defender"
        key_event = "attack culminated and broke"
    else:
        ratio = att_remaining / max(dfd_remaining, 1e-6)
        if ratio > STALEMATE_MARGIN:
            winner = "attacker"
        elif ratio < 1.0 / STALEMATE_MARGIN:
            winner = "defender"
        else:
            winner = "stalemate"
            key_event = "mutual attrition, lines held"

    ratio_end = att_remaining / max(dfd_remaining, 1e-6)
    decisive = ratio_end > DECISIVE_RATIO or ratio_end < 1.0 / DECISIVE_RATIO

    # Convert power-fraction losses into estimated personnel casualties,
    # scaled by each side's share of the combined initial power.
    total_power = att_power + dfd_power
    att_personnel = battle.attacker.strength * att_frac * (total_power and att_power / total_power * 2)
    dfd_personnel = battle.defender.strength * dfd_frac * (total_power and dfd_power / total_power * 2)

    return ChronosOutcome(
        winner=winner,
        attacker_casualties=min(att_personnel, battle.attacker.strength),
        defender_casualties=min(dfd_personnel, battle.defender.strength),
        duration_hours=duration if winner != "stalemate" else duration,
        decisive=decisive,
        key_event=key_event,
    )


def simulate_historical(battle: HistoricalBattle, universes: int = 500,
                        seed: Optional[int] = None,
                        overrides: Optional[dict] = None) -> dict:
    """Monte Carlo a historical battle. Returns outcome distribution + fidelity inputs."""
    seed = seed if seed is not None else 42
    overrides = overrides or {}

    def one(branch_seed: int) -> dict:
        outcome = resolve_battle(battle, branch_seed, overrides)
        return {
            "outcome": outcome.winner,
            "score": outcome.decisive,
            "attacker_casualties": outcome.attacker_casualties,
            "defender_casualties": outcome.defender_casualties,
            "key_event": outcome.key_event,
        }

    branches = monte_carlo_branch(one, universes, seed)
    wins = {"attacker": 0, "defender": 0, "stalemate": 0}
    att_cas = dfd_cas = 0.0
    for b in branches:
        wins[b["outcome"]] += 1
        att_cas += b["attacker_casualties"]
        dfd_cas += b["defender_casualties"]
    n = len(branches)

    # Doctrinal attribution - who fought with which published/practiced method.
    att_doc = resolve_doctrine(
        overrides.get("attacker_doctrine") or (battle.attacker.actors[0] if battle.attacker.actors else ""),
        battle.year,
    )
    dfd_doc = resolve_doctrine(
        overrides.get("defender_doctrine") or (battle.defender.actors[0] if battle.defender.actors else ""),
        battle.year,
    )
    doctrines_out = {
        "attacker": None if att_doc.key == "generic-contemporary" else att_doc.to_dict(),
        "defender": None if dfd_doc.key == "generic-contemporary" else dfd_doc.to_dict(),
    }
    return {
        "battle_key": battle.battle_key,
        "name": battle.name,
        "year": battle.year,
        "era": battle.era.name,
        "universes": n,
        "win_distribution": {k: v / n for k, v in wins.items()},
        "predicted_winner": max(wins, key=wins.get),
        "convergence": convergence_rate(branches),
        "avg_attacker_casualties": att_cas / n,
        "avg_defender_casualties": dfd_cas / n,
        "actual_winner": battle.actual_winner,
        "actual_attacker_casualty_ratio": (
            battle.attacker.casualties / battle.attacker.strength
            if battle.attacker.strength else None
        ),
        "actual_defender_casualty_ratio": (
            battle.defender.casualties / battle.defender.strength
            if battle.defender.strength else None
        ),
        "overrides": overrides or {},
        "doctrines": doctrines_out,
    }


def what_if(battle: HistoricalBattle, overrides: dict, universes: int = 500,
            seed: Optional[int] = None) -> dict:
    """Run a counterfactual branch set and diff it against the baseline replay.

    Supported override variables:
      attacker_strength_mult / defender_strength_mult  (float)
      attacker_quality_add / defender_quality_add       (float)
      terrain                                           (str)
      attacker_doctrine / defender_doctrine             (actor name swap)
    """
    baseline = simulate_historical(battle, universes, seed)
    counterfactual = simulate_historical(battle, universes, seed, overrides=overrides)
    return {
        "battle_key": battle.battle_key,
        "baseline": baseline,
        "counterfactual": counterfactual,
        "delta": {
            "winner_shift": f"{baseline['predicted_winner']} -> {counterfactual['predicted_winner']}",
            "win_prob_change": {
                k: round(counterfactual["win_distribution"][k] - baseline["win_distribution"][k], 4)
                for k in ("attacker", "defender", "stalemate")
            },
            "attacker_casualty_change_pct": round(
                (counterfactual["avg_attacker_casualties"] - baseline["avg_attacker_casualties"])
                / max(baseline["avg_attacker_casualties"], 1e-6) * 100, 2),
        },
    }
