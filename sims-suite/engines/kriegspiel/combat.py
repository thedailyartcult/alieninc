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
)


# Per-terrain parameter overrides written by the self-learning layer
# (engines.kriegspiel.learning.self_improve). Keyed ``(doctrine.value,
# terrain.value)`` -> partial param dict. Base doctrine identity lives in
# ``_DOCTRINE_PARAMS`` and is NEVER mutated at runtime, so a lesson learned in
# one theater cannot silently rewrite behavior everywhere else (the old
# global-mutation design let one wetland cell homogenize every doctrine).
_TERRAIN_PARAM_OVERRIDES: dict[tuple[str, str], dict] = {}


def get_doctrine_params(doctrine: Doctrine, terrain: TerrainType) -> dict:
    """Effective doctrine parameters for a specific terrain.

    Returns the base profile, or base merged with the learning layer's
    terrain-specific override when one exists. Read via this accessor
    everywhere combat resolves, so learned adjustments actually apply where
    they were earned and nowhere else.
    """
    base = _DOCTRINE_PARAMS.get(doctrine, _DOCTRINE_PARAMS[Doctrine.ATTRITION])
    override = _TERRAIN_PARAM_OVERRIDES.get(
        (getattr(doctrine, "value", doctrine), getattr(terrain, "value", terrain))
    )
    if not override:
        return base
    merged = dict(base)
    merged.update(override)
    return merged


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


# Logistics / EW constants. Kept here so the adherence probes can reference
# the same numbers the combat loop uses.
_LOGISTICS_RADIUS_KM = 30.0   # supply-regeneration projection range
_EW_RANGE_KM = 50.0           # cyber/EW jamming reach (recon-grade LOS)
_EW_JAM_TARGETS = 3           # max units one CYBER unit can degrade per tick
# Jam intensity: must be strong enough to matter inside short withdrawal-
# bounded battles (~3-5 ticks). ~4.5 morale/hit x 3 hits per cyber unit
# erodes enemy cohesion visibly within 2-3 ticks without instantly breaking
# anyone (a full rout still requires combat pressure on top of jamming).
_EW_JAM_DRAIN = (3.0, 6.0)


def _apply_logistics(force: Force, rng: random.Random) -> None:
    """LOGISTICS trains regenerate supply for nearby friendlies.

    Gives LOGISTICAL doctrine its identity as sustainment warfare: a force
    that keeps its trucks rolling fights at high effectiveness deep into a
    battle while its opponent's supply (and therefore combat power) bleeds
    out. Without this mechanic LOGISTICS units were just weak riflemen and
    the doctrine's supply_focus parameter had no physical carrier.
    """
    trains = [u for u in force.units
              if u.unit_type is UnitType.LOGISTICS
              and u.strength > 0 and u.morale > 10]
    if not trains:
        return
    consumers = [u for u in force.units
                 if u.unit_type is not UnitType.LOGISTICS and u.strength > 0]
    for train in trains:
        tlat, tlng = train.position
        for unit in consumers:
            ulat, ulng = unit.position
            if haversine_km(tlat, tlng, ulat, ulng) <= _LOGISTICS_RADIUS_KM:
                # Regen comfortably exceeds typical drain (~0.25-0.6/tick for
                # high-supply_focus doctrines) so sustained logistics flips
                # late-battle effectiveness — that's the doctrinal point.
                unit.supply = min(100.0, unit.supply + rng.uniform(1.0, 2.5))


def _apply_ew_suppression(
    attacker: Force,
    defender: Force,
    terrain: TerrainType,
    rng: random.Random,
) -> int:
    """CYBER/EW units jam enemy command links: morale attrition, not hulls.

    Electronic warfare degrades *cohesion* — jammed units fight less willing-
    ly. Implemented as direct morale drain on up to ``_EW_JAM_TARGETS``
    enemy units per cyber unit within recon-grade LOS, which feeds the
    existing effective-strength and fighting-willingness gates (units below
    morale 25 stop counting for breakthrough margins; below 10 they stop
    fighting entirely). Returns total jamming events for probes/tests.
    """
    events = 0
    for c_unit in attacker.units:
        if (c_unit.unit_type is not UnitType.CYBER
                or c_unit.strength <= 0 or c_unit.morale <= 10):
            continue
        clat, clng = c_unit.position
        targets = [u for u in defender.units if u.strength > 0]
        rng.shuffle(targets)
        hits = 0
        for target in targets:
            if hits >= _EW_JAM_TARGETS:
                break
            tlat, tlng = target.position
            dist = haversine_km(clat, clng, tlat, tlng)
            if dist > _EW_RANGE_KM or not has_line_of_sight(terrain, dist, UnitType.RECON):
                continue
            target.morale = max(0.0, target.morale - rng.uniform(*_EW_JAM_DRAIN))
            hits += 1
        events += hits
    return events


def simulate_battle(battle: Battle, seed: Optional[int] = None) -> BattleOutcome:
    """Simulate one complete battle and return the outcome.

    This is the per-branch function. ``scenarios.py`` calls this 10k times
    with different seeds, varying doctrine and stochastic events each time.
    Thin wrapper over :func:`_simulate_forces` — the campaign layer calls
    that core directly so unit states carry across engagements.
    """
    # NOTE: ``seed or battle.seed or 42`` treated seed=0 as "unset" — a real
    # seed of 0 silently produced battle.seed's (or 42's) trajectory. Use
    # explicit None checks so every integer seed, including 0, is distinct.
    if seed is not None:
        rng_seed = seed
    elif battle.seed is not None:
        rng_seed = battle.seed
    else:
        rng_seed = 42
    red = _clone_force(battle.red_force)
    blue = _clone_force(battle.blue_force)
    outcome, _, _ = _simulate_forces(
        red, blue, battle.battlefield,
        duration_hours=battle.duration_hours, seed=rng_seed,
    )
    return outcome


def _simulate_forces(
    red: Force,
    blue: Force,
    battlefield: Battlefield,
    duration_hours: int,
    seed: int,
) -> tuple[BattleOutcome, Force, Force]:
    """Core combat loop operating on caller-owned forces.

    Mutates ``red``/``blue`` in place (the caller owns them — the campaign
    layer passes its persistent force objects through so attrition carries
    between engagements) and returns ``(outcome, red, blue)``. Initial
    effective strengths for the casualty report are captured at entry, i.e.
    relative to whatever state the caller handed in.
    """
    rng = random.Random(seed)
    terrain = battlefield.terrain
    red_params = get_doctrine_params(red.doctrine, terrain)
    blue_params = get_doctrine_params(blue.doctrine, terrain)

    hours_elapsed = 0.0
    tick_hours = 6.0  # each tick = 6 hours of battle (fewer ticks = faster)
    key_event = ""
    decisive = False
    breakthrough_by = ""
    withdrawn_by = ""

    # Initial effective strengths — the denominators for both the casualty
    # report and the mid-battle culmination check.
    red_init_eff = red.effective_strength(terrain)
    blue_init_eff = blue.effective_strength(terrain)
    # A force that has lost this share of its initial combat power while NOT
    # bleeding less than the enemy disengages: it has reached its culminating
    # point. Without a withdrawal mechanic every fight resolved to total
    # annihilation, which structurally favored whichever side could out-kill
    # in an endgame neither side would have fought in reality.
    _WITHDRAWAL_PCT = 35.0

    for tick in range(int(duration_hours / tick_hours)):
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

        # --- logistics sustainment (after drain, so trains visibly offset it)
        _apply_logistics(red, rng)
        _apply_logistics(blue, rng)

        # --- EW / cyber suppression: jamming degrades enemy cohesion ---
        if rng.random() < 0.5:
            _apply_ew_suppression(red, blue, terrain, rng)
            _apply_ew_suppression(blue, red, terrain, rng)
        else:
            _apply_ew_suppression(blue, red, terrain, rng)
            _apply_ew_suppression(red, blue, terrain, rng)

        # --- movement: units close into engagement range ---
        _advance_units(red, blue, battlefield, terrain, tick_hours, rng)
        _advance_units(blue, red, battlefield, terrain, tick_hours, rng)

        # --- engagements ---
        # One mutual-firefight round per tick. Historically this ran twice
        # (red-initiated, then blue-initiated) with asymmetric damage tables
        # (attacker rolled 2-8, defender returned 1-5), which baked an
        # attack-dominant bias into every exchange and made low-aggression
        # doctrines take suicidal self-damage in their own attack rounds.
        # Who initiates targeting is still random per tick so neither side
        # owns the kill-capture order.
        if rng.random() < 0.5:
            _resolve_engagements(red, blue, terrain, rng)
        else:
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
        #
        # Side order is shuffled every tick: red used to be checked first,
        # so when both sides qualified in the same tick red always converted
        # first (a measurable mirror-match skew).
        _breakthrough_sides = [
            ("red", red, blue, red_params), ("blue", blue, red, blue_params),
        ]
        rng.shuffle(_breakthrough_sides)
        # Sustained-pressure gate: no breakthrough conversions in the opening
        # exchange (~first 15% of planned battle). Tick-1 conversions let
        # whichever side rolled slightly better instantly turn a one-unit
        # lead into a total morale collapse (-40 to every defender). Real
        # penetrations exploit defenses weakened by at least one round of
        # sustained combat; combined with the >=25% local-margin requirement,
        # only genuine local superiority converts.
        _bt_allowed_from = duration_hours * 0.15
        for side, attacker, defender, params in _breakthrough_sides:
            if breakthrough_by:
                break
            if hours_elapsed < _bt_allowed_from:
                continue
            bt = params.get("breakthrough", 0.0)
            if bt <= 0:
                continue
            atk_fighting = [u for u in attacker.units if u.strength > 40 and u.morale > 25]
            def_fighting = [u for u in defender.units if u.strength > 40 and u.morale > 25]
            if not atk_fighting or not def_fighting:
                continue
            local_margin = (len(atk_fighting) - len(def_fighting)) / max(len(def_fighting), 1)
            # A genuine breakthrough requires DECISIVE local superiority
            # (~25%+ more fighting units), not a transient one-unit lead.
            # The old ``<= 0`` gate let high-breakthrough doctrines convert
            # random early fluctuations into automatic morale collapses,
            # which is what kept prepared defenses from ever holding.
            if local_margin < 0.25:
                continue
            # Probability from doctrine emphasis, scaled by the depth of the
            # local edge (capped so overwhelming collapses stay probable).
            prob = bt * min(local_margin, 0.75)
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

        # --- culmination / withdrawal ---
        # Evaluated AFTER collapse checks so genuine annihilations still
        # register as decisive wins. A side that has burned >=35% of its
        # initial combat power while bleeding at least as much as the enemy
        # disengages — the attack has culminated. Both sides crossing in the
        # same tick is a mutual pull-back (stalemate).
        red_loss_pct = max(0.0, (1 - red_strength / max(red_init_eff, 1)) * 100)
        blue_loss_pct = max(0.0, (1 - blue_strength / max(blue_init_eff, 1)) * 100)
        red_culminated = red_loss_pct >= _WITHDRAWAL_PCT and red_loss_pct >= blue_loss_pct
        blue_culminated = blue_loss_pct >= _WITHDRAWAL_PCT and blue_loss_pct >= red_loss_pct
        if red_culminated or blue_culminated:
            withdrawn_by = "both" if (red_culminated and blue_culminated) else (
                "red" if red_culminated else "blue")
            if withdrawn_by == "red":
                key_event = "red force withdrew — the attack culminated"
            elif withdrawn_by == "blue":
                key_event = "blue force withdrew — the attack culminated"
            else:
                key_event = "both forces disengaged after mutual attrition"
            break

    # --- determine winner ---
    red_final = red.effective_strength(terrain)
    blue_final = blue.effective_strength(terrain)
    red_initial = red_init_eff
    blue_initial = blue_init_eff

    red_casualties = max(0, (1 - red_final / red_initial) * 100) if red_initial else 100
    blue_casualties = max(0, (1 - blue_final / blue_initial) * 100) if blue_initial else 100

    if withdrawn_by == "both":
        winner = "stalemate"
        decisive = False
    elif withdrawn_by == "red":
        # Red disengaged: blue holds the field. A repulse is a clear tactical
        # result but not an annihilation.
        winner = "blue"
        decisive = False
    elif withdrawn_by == "blue":
        winner = "red"
        decisive = False
    elif red_final > blue_final * 1.3:
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
        withdrawn_by=withdrawn_by,
    ), red, blue


def _clone_force(force: Force) -> Force:
    """Deep-clone a force so the original isn't mutated across branches.

    Also sanitizes numeric fields on the procedural path (the LLM path has
    validator.py bounds, but direct API callers had none): NaN/inf revert to
    the dataclass defaults and negatives clamp to 0. Without this a single
    NaN strength silently propagated through every comparison and produced
    ghost "stalemate" outcomes.
    """

    def _san(value: float, default: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return float(default)
        if v != v or v in (float("inf"), float("-inf")):
            return float(default)
        return max(0.0, v)

    return Force(
        name=force.name,
        doctrine=force.doctrine,
        side=force.side,
        units=[Unit(
            unit_type=u.unit_type,
            strength=_san(u.strength, 100.0),
            morale=_san(u.morale, 80.0),
            supply=_san(u.supply, 100.0),
            position=u.position if u.position and all(
                isinstance(c, (int, float)) and c == c for c in u.position
            ) else (0.0, 0.0),
            speed_kmh=max(0.1, _san(u.speed_kmh, 30.0)),
            engagement_range_km=max(0.1, _san(u.engagement_range_km, 5.0)),
        ) for u in force.units],
    )


def _advance_units(
    force: Force,
    enemy: Force,
    battlefield: Battlefield,
    terrain: TerrainType,
    hours: float,
    rng: random.Random,
) -> None:
    """Move a force's mobile units into contact with the enemy.

    Historical bug (found by adversarial testing): units advanced at real
    speed (~180 km per 6h tick) but were clamped to ``mid ± 5%`` of the
    *theater* bounds. On theater-scale battlefields that clamp sits tens of
    kilometers from the tactical deployment zone, so both forces teleported
    past each other on tick 1 and then sat ~130 km apart, out of range, for
    the rest of the battle. Infantry and armor engaged zero times in 300
    instrumented battles — every "battle" was a stationary artillery/air
    duel plus attrition drift.

    Fix: converge-to-contact. Mobile units advance toward the enemy
    centroid and halt when within fighting distance (~1 km), so combat is
    sustained every tick instead of a single opening volley. Artillery and
    air hold position (they already outrange the meeting line).
    """
    del battlefield, terrain  # movement is relative to the enemy, not the box
    targets = [u.position for u in enemy.units if u.strength > 0]
    if not targets:
        return
    tgt_lat = sum(p[0] for p in targets) / len(targets)
    tgt_lng = sum(p[1] for p in targets) / len(targets)
    # Halt offset: ~1 km so units close to contact but don't stack on the
    # exact enemy centroid.
    hold_deg = 0.009

    for unit in force.units:
        if unit.strength <= 0 or unit.morale <= 10:
            continue
        # Units only need to close the gap; artillery/recon hold position.
        if unit.unit_type in (UnitType.ARTILLERY, UnitType.AIR):
            continue
        lat, lng = unit.position
        dlat = tgt_lat - lat
        dlng = tgt_lng - lng
        dist_deg = (dlat * dlat + dlng * dlng) ** 0.5
        if dist_deg <= hold_deg:
            continue  # already in contact — hold and fight
        step_deg = min(unit.speed_kmh * hours / 111.0, dist_deg - hold_deg)
        unit.position = (
            lat + dlat / dist_deg * step_deg,
            lng + dlng / dist_deg * step_deg,
        )


def _resolve_engagements(
    attacker: Force,
    defender: Force,
    terrain: TerrainType,
    rng: random.Random,
) -> None:
    """Resolve one tick of mutual-fire engagements between two forces.

    Each in-range pair is a FIREFIGHT, not a one-directional strike: both
    units shoot. Combat power on each side is the unit's terrain-adjusted
    effectiveness scaled by its doctrine's relevant posture:

      - the firing side projects ``aggression`` (how much fire it puts out);
      - the receiving side defends with ``posture`` — its own supply_focus
        read as preparation/fortification/logistic readiness (bounded
        [1.0, 1.4]) reduced by the attacker's suppression (risk × 0.3).

    Both damage rolls use the SAME uniform(2,8) table. The old asymmetric
    tables (attack 2-8 vs return 1-5) made attacking strictly better
    independent of doctrine, so SHOCK beat prepared defenses ~100% at parity.
    Now the exchange ratio follows combat power: cracking a prepared defense
    requires either a doctrine that generates real assault power (SHOCK) or
    numbers (Lanchester-style mass) — matching the military-science baseline
    that the defender holds the advantage at parity.

    A unit engages every enemy within range this tick, capped at 3 targets
    for performance (10k scenarios). Casualties apply immediately, so
    mid-round losses remove units from further exchanges this tick.
    """
    atk_params = get_doctrine_params(attacker.doctrine, terrain)
    def_params = get_doctrine_params(defender.doctrine, terrain)
    # Calibrated posture multiplier [1.0, 1.54]: a fully-logistic doctrine
    # (LOGISTICAL sf=.95) defends at ~1.54x effectiveness, a bare-bones one
    # (GUERRILLA sf=.5) at 1.0x. Slope chosen so that at force parity a
    # prepared defense roughly breaks even on casualties against SHOCK
    # (validated empirically post-fix); cracking it requires numbers.
    def_posture = 0.4 + 1.2 * def_params["supply_focus"]
    suppression = 1 - atk_params["risk"] * 0.3
    max_range = max((u.engagement_range_km for u in attacker.units), default=15.0)

    # Two-pass simultaneous resolution (Lanchester-style aimed fire):
    #   pass 1 — every shooter picks up to 3 in-range/LOS targets and accrues
    #            pending outgoing damage; count shooters per target.
    #   pass 2 — apply all damage simultaneously; each target's RETURN fire is
    #            its full exchange shot SPLIT across however many shooters
    #            engaged it (one unit has one unit's worth of fire).
    #
    # Targeting order is randomized per round: list-order selection made all
    # shooters pile onto the first units in the array (a death-cascade where
    # 3 units absorbed an entire army's fire every tick).
    #
    # Return-fire capability uses ``max(aggression, posture*0.6)``: prepared
    # troops fight back from their positions even when doctrinally passive.
    # The old pure-aggression projection meant DEFENSIVE (aggression 0.3)
    # could absorb fire but literally could not shoot, so any forced-decision
    # battle resolved to "defense eventually loses" regardless of posture.
    pending: dict[int, list] = []   # [defender, dmg, [(shooter, shooter_eff)]]
    pool = [u for u in defender.units if u.strength > 0]
    # Each shooter gets its own random rotation through the target pool.
    # A single shared shuffle was not enough: every shooter then walked the
    # same permuted order and the first 3 units absorbed the entire army's
    # fire every tick (death-cascade). Independent offsets spread fire
    # roughly uniformly across the enemy line.
    pool_len = len(pool)
    for a_unit in attacker.units:
        if a_unit.strength <= 0 or a_unit.morale <= 10:
            continue
        alat, alng = a_unit.position
        engagements = 0
        start = rng.randrange(pool_len) if pool_len else 0
        for k in range(pool_len):
            d_unit = pool[(start + k) % pool_len]
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

            a_eff = a_unit.effective_strength(terrain)
            d_eff = d_unit.effective_strength(terrain)
            pow_atk = a_eff * atk_params["aggression"]
            pow_def = d_eff * def_posture * suppression

            damage_to_defender = (pow_atk / max(pow_def, 1)) * rng.uniform(2, 8)
            for entry in pending:
                if entry[0] is d_unit:
                    entry[1] += damage_to_defender
                    entry[2].append((a_unit, a_eff))
                    break
            else:
                pending.append([d_unit, damage_to_defender, [(a_unit, a_eff)]])
            engagements += 1

    # pass 2 — simultaneous mutual exchange per contact pair.
    # Each pair trades ONCE per tick: the shooting side projects
    # ``aggression``-scaled fire resisted by posture+suppression; the target
    # returns fire with ``max(aggression, posture*0.75)`` (prepared troops
    # fight back from positions even when doctrinally passive — without this
    # floor, low-aggression doctrines could absorb fire but never kill, so
    # any forced-decision battle resolved to "the passive side loses").
    # Because both damage terms live in the SAME pair exchange, there is no
    # "initiative phase" a passive side donates free kills during.
    # Calibrated so that at force parity a prepared defense (high supply_focus)
    # wins the per-pair exchange decisively (~1.5:1) against SHOCK — matching
    # the military-science baseline that cracking a prepared defense needs
    # numbers (the cap-3 retaliation lets massed attackers saturate a thinning
    # line, preserving the square-law advantage of ~2x+ force ratios).
    retaliation_fp = max(def_params["aggression"], def_posture * 1.1)
    for d_unit, total_damage, shooters in pending:
        d_eff = d_unit.effective_strength(terrain)
        for a_unit, a_eff in shooters[:3]:
            damage_to_attacker = (
                (d_eff * retaliation_fp) / max(a_eff, 1)
            ) * rng.uniform(2, 8)
            a_unit.strength = max(0, a_unit.strength - damage_to_attacker)
            if a_unit.strength <= 0:
                a_unit.morale = max(0, a_unit.morale - 20)
        d_unit.strength = max(0, d_unit.strength - total_damage)
        if d_unit.strength <= 0:
            d_unit.morale = max(0, d_unit.morale - 20)
        if d_unit.strength <= 0:
            d_unit.morale = max(0, d_unit.morale - 20)
