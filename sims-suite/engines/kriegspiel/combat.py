"""Kriegspiel combat simulation — movement, engagement, logistics.

Simulates one branched battle: forces maneuver, engage, and degrade over time.
Each tick represents a time step (configurable). The simulation is stochastic —
doctrine choices, engagement outcomes, and morale/supply attrition are all
randomized so each branch produces a different outcome.

This is the per-branch function that ``scenarios.py`` calls 10,000 times via
the shared ``monte_carlo_branch()`` primitive.
"""

from __future__ import annotations

import random
from typing import Optional

from engines.kriegspiel.models import (
    Battle,
    BattleOutcome,
    Battlefield,
    Doctrine,
    Force,
    TerrainType,
    Unit,
    UnitType,
)
from engines.kriegspiel.geography import (
    haversine_km,
    has_line_of_sight,
    terrain_speed_modifier,
)


# Doctrine parameters — each doctrine biases the simulation differently
_DOCTRINE_PARAMS = {
    Doctrine.ATTRITION:     {"aggression": 0.7, "risk": 0.5, "supply_focus": 0.6, "morale_drain": 0.8},
    Doctrine.MANEUVER:      {"aggression": 0.8, "risk": 0.7, "supply_focus": 0.5, "morale_drain": 0.6},
    Doctrine.SHOCK:         {"aggression": 0.95, "risk": 0.9, "supply_focus": 0.4, "morale_drain": 1.0},
    Doctrine.DEFENSIVE:     {"aggression": 0.3, "risk": 0.2, "supply_focus": 0.8, "morale_drain": 0.5},
    Doctrine.GUERRILLA:     {"aggression": 0.5, "risk": 0.6, "supply_focus": 0.3, "morale_drain": 0.4},
    Doctrine.LOGISTICAL:    {"aggression": 0.4, "risk": 0.4, "supply_focus": 0.95, "morale_drain": 0.6},
    Doctrine.INFORMATION:   {"aggression": 0.3, "risk": 0.3, "supply_focus": 0.7, "morale_drain": 0.3},
}

# Key events for narrative flavor. This is a *mutable* pool — the LLM
# synthesis layer can append situational events via ``register_events()``.
# The procedural baseline stays the same; LLM events simply add variety.
_KEY_EVENTS: list[str] = [
    "flanking maneuver succeeded",
    "supply convoy intercepted",
    "artillery barrage broke enemy lines",
    "air superiority achieved",
    "night assault overwhelmed defenders",
    "logistics collapse forced retreat",
    "cyber disruption disabled comms",
    "reinforcements arrived at critical moment",
    "terrain forced column into chokepoint",
    "morale broke under sustained pressure",
    "reconnaissance revealed weak flank",
    "naval blockade cut reinforcement route",
]


def register_events(events: list[str]) -> None:
    """Append situational events to the runtime event pool.

    Called by the LLM synthesis layer when a battle seed includes
    ``situational_events`` or when ``synthesize_events()`` is invoked.
    De-duplicates against the existing pool so repeat calls are safe.
    """
    existing = set(_KEY_EVENTS)
    for e in events:
        if isinstance(e, str) and e not in existing:
            _KEY_EVENTS.append(e)
            existing.add(e)


def get_event_pool() -> list[str]:
    """Return the current event pool (procedural + any LLM-registered)."""
    return list(_KEY_EVENTS)


def simulate_battle(battle: Battle, seed: Optional[int] = None) -> BattleOutcome:
    """Simulate one complete battle and return the outcome.

    This is the per-branch function. ``scenarios.py`` calls this 10k times
    with different seeds, varying doctrine and stochastic events each time.
    """
    rng = random.Random(seed or battle.seed or 42)
    terrain = battle.battlefield.terrain
    red = _clone_force(battle.red_force)
    blue = _clone_force(battle.blue_force)
    red_params = _DOCTRINE_PARAMS.get(red.doctrine, _DOCTRINE_PARAMS[Doctrine.ATTRITION])
    blue_params = _DOCTRINE_PARAMS.get(blue.doctrine, _DOCTRINE_PARAMS[Doctrine.ATTRITION])

    hours_elapsed = 0.0
    tick_hours = 6.0  # each tick = 6 hours of battle (fewer ticks = faster)
    key_event = ""
    decisive = False

    for tick in range(int(battle.duration_hours / tick_hours)):
        hours_elapsed += tick_hours

        # --- supply attrition ---
        for force, params in [(red, red_params), (blue, blue_params)]:
            drain = (1 - params["supply_focus"]) * rng.uniform(0.5, 2.0)
            for unit in force.units:
                unit.supply = max(0, unit.supply - drain)

        # --- morale drift ---
        for force, params in [(red, red_params), (blue, blue_params)]:
            drain = params["morale_drain"] * rng.uniform(0.3, 1.5)
            for unit in force.units:
                unit.morale = max(0, unit.morale - drain)

        # --- engagements ---
        _resolve_engagements(red, blue, terrain, rng)
        _resolve_engagements(blue, red, terrain, rng)

        # --- record key events ---
        if not key_event and rng.random() < 0.15:
            key_event = rng.choice(_KEY_EVENTS)

        # --- check for decisive outcome ---
        red_strength = red.effective_strength(terrain)
        blue_strength = blue.effective_strength(terrain)
        if red_strength < blue_strength * 0.2:
            decisive = True
            break
        if blue_strength < red_strength * 0.2:
            decisive = True
            break

    # --- determine winner ---
    red_final = red.effective_strength(terrain)
    blue_final = blue.effective_strength(terrain)
    red_initial = battle.red_force.effective_strength(terrain)
    blue_initial = battle.blue_force.effective_strength(terrain)

    red_casualties = max(0, (1 - red_final / red_initial) * 100) if red_initial else 100
    blue_casualties = max(0, (1 - blue_final / blue_initial) * 100) if blue_initial else 100

    if red_final > blue_final * 1.3:
        winner = "red"
    elif blue_final > red_final * 1.3:
        winner = "blue"
    elif red_final > blue_final * 1.05:
        winner = "red"
        decisive = False
    elif blue_final > red_final * 1.05:
        winner = "blue"
        decisive = False
    else:
        winner = "stalemate"

    terrain_advantage = "red" if red_final > blue_final else ("blue" if blue_final > red_final else "neutral")
    score = red_final - blue_final if winner == "red" else blue_final - red_final if winner == "blue" else 0.0

    return BattleOutcome(
        winner=winner,
        red_casualties_pct=round(red_casualties, 1),
        blue_casualties_pct=round(blue_casualties, 1),
        duration_hours=round(hours_elapsed, 1),
        decisive=decisive,
        key_event=key_event or "sustained engagement without decisive moment",
        terrain_advantage=terrain_advantage,
        score=round(score, 2),
        outcome=winner,
    )


def _clone_force(force: Force) -> Force:
    """Deep-clone a force so the original isn't mutated across branches."""
    return Force(
        name=force.name,
        doctrine=force.doctrine,
        side=force.side,
        units=[Unit(
            unit_type=u.unit_type,
            strength=u.strength,
            morale=u.morale,
            supply=u.supply,
            position=u.position,
            speed_kmh=u.speed_kmh,
            engagement_range_km=u.engagement_range_km,
        ) for u in force.units],
    )


def _resolve_engagements(
    attacker: Force,
    defender: Force,
    terrain: TerrainType,
    rng: random.Random,
) -> None:
    """Resolve one round of engagements between attacker and defender units."""
    params = _DOCTRINE_PARAMS.get(attacker.doctrine, _DOCTRINE_PARAMS[Doctrine.ATTRITION])
    max_range = max((u.engagement_range_km for u in attacker.units), default=15.0)
    for a_unit in attacker.units:
        if a_unit.strength <= 0 or a_unit.morale <= 10:
            continue
        alat, alng = a_unit.position
        for d_unit in defender.units:
            if d_unit.strength <= 0:
                continue
            dlat, dlng = d_unit.position
            if abs(dlat - alat) > max_range / 111 or abs(dlng - alng) > max_range / 111:
                continue
            dist = haversine_km(alat, alng, dlat, dlng)
            if dist > a_unit.engagement_range_km:
                continue
            if not has_line_of_sight(terrain, dist, a_unit.unit_type):
                continue

            a_eff = a_unit.effective_strength(terrain) * params["aggression"]
            d_eff = d_unit.effective_strength(terrain) * (1 - params["risk"] * 0.3)

            damage_to_defender = (a_eff / max(d_eff, 1)) * rng.uniform(2, 8)
            damage_to_attacker = (d_eff / max(a_eff, 1)) * rng.uniform(1, 5)

            d_unit.strength = max(0, d_unit.strength - damage_to_defender)
            a_unit.strength = max(0, a_unit.strength - damage_to_attacker)

            if d_unit.strength <= 0:
                d_unit.morale = max(0, d_unit.morale - 20)
            break  # one engagement per unit per tick
