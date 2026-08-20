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


# Doctrine parameters — each doctrine biases the simulation differently.
# ``breakthrough`` is the doctrinal emphasis on converting a local advantage
# into a decisive penetration rather than a long attrition grind. High-value
# for Shock/Maneuver, near-zero for Defensive. It is the mechanic that lets a
# high-aggression force *win* instead of merely bleeding out over the full
# battle duration.
#
# BALANCE NOTE (evidence-backed): in this combat model, `supply_focus` and
# `morale_drain` dominate outcomes because engagements are sparse relative to
# per-tick attrition. A doctrine that couples high aggression with very low
# supply_focus / very high morale_drain self-destructs before it can exploit
# its aggression. The profiles below keep each doctrine's identity (Shock =
# most aggressive/risky/breakthrough) while ensuring self-attrition is not so
# severe it guarantees defeat — verified via the win matrix + adherence probes.
_DOCTRINE_PARAMS = {
    Doctrine.ATTRITION:     {"aggression": 0.7, "risk": 0.5, "supply_focus": 0.6, "morale_drain": 0.8, "breakthrough": 0.40},
    Doctrine.MANEUVER:      {"aggression": 0.8, "risk": 0.7, "supply_focus": 0.55, "morale_drain": 0.6, "breakthrough": 0.60},
    Doctrine.SHOCK:         {"aggression": 0.95, "risk": 0.9, "supply_focus": 0.7, "morale_drain": 0.5, "breakthrough": 0.80},
    Doctrine.DEFENSIVE:     {"aggression": 0.3, "risk": 0.2, "supply_focus": 0.8, "morale_drain": 0.5, "breakthrough": 0.05},
    Doctrine.GUERRILLA:     {"aggression": 0.5, "risk": 0.6, "supply_focus": 0.5, "morale_drain": 0.4, "breakthrough": 0.35},
    Doctrine.LOGISTICAL:    {"aggression": 0.4, "risk": 0.4, "supply_focus": 0.95, "morale_drain": 0.6, "breakthrough": 0.15},
    Doctrine.INFORMATION:   {"aggression": 0.3, "risk": 0.3, "supply_focus": 0.7, "morale_drain": 0.3, "breakthrough": 0.20},
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
    breakthrough_by = ""

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

        # --- movement: units close into engagement range ---
        _advance_units(red, battle.battlefield, terrain, tick_hours, rng)
        _advance_units(blue, battle.battlefield, terrain, tick_hours, rng)

        # --- engagements ---
        _resolve_engagements(red, blue, terrain, rng)
        _resolve_engagements(blue, red, terrain, rng)

        # --- breakthrough check: a high-breakthrough attacker that is winning
        # its local engagements can convert that into a decisive penetration and
        # end the battle early, rather than grinding to the 48-tick limit. This
        # is what makes Shock/Maneuver able to *win* instead of bleeding out.
        #
        # The trigger is *local*: count how many attacker units remain at high
        # effectiveness vs defender units. A force that has destroyed more of
        # the enemy's fighting units than it has lost of its own holds a local
        # superiority a breakthrough doctrine can exploit. Global strength
        # ratio is a poor trigger here because the engagement-starved model
        # rarely moves it past 1.0; unit attrition is the real signal.
        for side, attacker, defender, params in (
            ("red", red, blue, red_params), ("blue", blue, red, blue_params),
        ):
            if breakthrough_by:
                break
            bt = params.get("breakthrough", 0.0)
            if bt <= 0:
                continue
            atk_fighting = [u for u in attacker.units if u.strength > 40 and u.morale > 25]
            def_fighting = [u for u in defender.units if u.strength > 40 and u.morale > 25]
            if not atk_fighting or not def_fighting:
                continue
            local_margin = (len(atk_fighting) - len(def_fighting)) / max(len(def_fighting), 1)
            # Only a genuine local edge (more fighting units than the defender)
            # can be exploited; a symmetric count cannot.
            if local_margin <= 0:
                continue
            # Probability from doctrine emphasis, amplified by the local edge.
            prob = bt * (0.15 + min(local_margin, 0.5))
            if rng.random() < prob:
                decisive = True
                breakthrough_by = side
                # A breakthrough shatters the defender's coherence.
                for unit in defender.units:
                    unit.morale = max(0, unit.morale - 40)
                if side == "red":
                    key_event = "red force achieved a decisive breakthrough"
                else:
                    key_event = "blue force achieved a decisive breakthrough"
                break

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

    def _avg_pct(force: Force, attr: str) -> float:
        units = [u for u in force.units if getattr(u, "strength", 0) > 0]
        if not units:
            return 0.0
        return sum(getattr(u, attr, 0.0) for u in units) / (len(units) * 100.0)

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
        red_final_supply_pct=round(_avg_pct(red, "supply"), 4),
        red_final_morale_pct=round(_avg_pct(red, "morale"), 4),
        blue_final_supply_pct=round(_avg_pct(blue, "supply"), 4),
        blue_final_morale_pct=round(_avg_pct(blue, "morale"), 4),
        breakthrough_by=breakthrough_by,
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


def _advance_units(
    force: Force,
    battlefield: Battlefield,
    terrain: TerrainType,
    hours: float,
    rng: random.Random,
) -> None:
    """Move a force's units toward the enemy edge so they close into
    engagement range.

    Forces deploy on opposite edges and previously never moved, so most units
    (especially infantry, LOS ~5km) were permanently out of range — combat
    barely happened and per-tick supply/morale attrition dominated every
    outcome. Advancing units makes the doctrine's aggression *actually engage*,
    which is the correct rebalance for the 'supply_focus meta'.
    """
    w, s, e, n = battlefield.bounds
    # Red deploys west (lng ~ w), advances east; blue deploys east, advances west.
    direction = 1.0 if force.side == "red" else -1.0
    field_width = max(e - w, 1e-6)

    for unit in force.units:
        if unit.strength <= 0 or unit.morale <= 10:
            continue
        # Units only need to close the gap; artillery/recon hold position.
        if unit.unit_type in (UnitType.ARTILLERY, UnitType.AIR):
            continue
        speed = unit.speed_kmh * terrain_speed_modifier(terrain, unit.unit_type)
        # Fraction of the field width covered in this tick.
        lat, lng = unit.position
        step_lng = direction * (speed * hours / 111.0) / field_width * (e - w)
        # Units don't close infinitely fast; advance at most toward the midpoint.
        new_lng = lng + step_lng
        # Clamp so red never crosses past center by much and blue stays in its half.
        mid = w + (e - w) * 0.5
        if force.side == "red":
            new_lng = min(new_lng, mid + (e - w) * 0.05)
        else:
            new_lng = max(new_lng, mid - (e - w) * 0.05)
        unit.position = (lat, new_lng)


def _resolve_engagements(
    attacker: Force,
    defender: Force,
    terrain: TerrainType,
    rng: random.Random,
) -> None:
    """Resolve one round of engagements between attacker and defender units.

    A unit engages every defender within range this tick (not just one), so
    aggression meaningfully concentrates fire and combat isn't starved to a
    single engagement per tick. Capped per unit for performance (10k scenarios).
    """
    params = _DOCTRINE_PARAMS.get(attacker.doctrine, _DOCTRINE_PARAMS[Doctrine.ATTRITION])
    max_range = max((u.engagement_range_km for u in attacker.units), default=15.0)
    for a_unit in attacker.units:
        if a_unit.strength <= 0 or a_unit.morale <= 10:
            continue
        alat, alng = a_unit.position
        engagements = 0
        for d_unit in defender.units:
            if engagements >= 3:   # cap: concentrate but bound cost
                break
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
            engagements += 1
