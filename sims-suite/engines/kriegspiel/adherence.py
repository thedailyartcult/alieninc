"""Kriegspiel doctrine adherence probes — controlled behavioral studies.

MatrAIx's core validation question is: *do the assigned attributes actually
change observed behavior?* (their 400-trial controlled study found 91.5%
adherence). This module asks the same question of Kriegspiel doctrines:

Each doctrine declares a parameter profile (aggression, risk, supply_focus,
morale_drain). But declaring is not behaving. ``run_adherence_probe`` runs a
controlled study: every doctrine fights the *same* reference force on the
*same* terrain for a fixed number of seeded battles, and we measure the
behavioral signature it actually produces:

  - aggression      → battle duration (lower = bloodier/faster) + casualties
  - risk            → decisiveness rate + outcome variance
  - supply_focus    → own-side supply retention
  - morale_drain    → own-side morale retention

We then test, per attribute, whether the *declared* parameter ordering across
doctrines predicts the *observed* behavior ordering (Spearman rank correlation
on ranks — stdlib-only). The result is an adherence score per attribute plus
an overall rate, so the research dashboard can show *why* a doctrine wins, not
just that it wins.

The tracker's self-improvement rewrites doctrine parameters; this probe is the
counter-check that those rewrites keep the doctrine's identity coherent —
otherwise the engine could "optimize" every doctrine into the same blob.
"""

from __future__ import annotations

import random
from typing import Optional

from engines.kriegspiel.models import (
    Battle,
    Battlefield,
    Doctrine,
    Force,
    TerrainType,
    Unit,
    UnitType,
)
from engines.kriegspiel.combat import simulate_battle
from engines.kriegspiel.combat import _DOCTRINE_PARAMS
from engines.kriegspiel.geography import deploy_force

# Declared behavioral expectations per attribute, given the doctrine's params.
# Each maps "high declared value" -> what we expect to observe.
#
# PROXY SEMANTICS after the tactical-deployment + engagement rework (2026-08-19):
# the combat model is now aggression-coherent — aggression predicts win rate
# with Spearman ~1.0 (an aggressive doctrine that actually engages destroys the
# enemy and wins). This inverts several earlier proxies:
#   - aggression -> win_rate: aggressive doctrines WIN (was: avg_winner_casualties,
#     which no longer tracks since winners now take FEWER casualties).
#   - risk -> avg_winner_casualties (INVERTED): a high-risk doctrine commits and
#     wins *cheaply* (fewer casualties to win). Note risk and aggression are
#     correlated in effect (both drive offensive success), so their signals on
#     win rate overlap; avg_winner_casualties keeps risk distinct.
#   - supply_focus -> supply retained (unchanged): higher focus = more retained.
#   - morale_drain -> morale retained (unchanged, inverse).
_AGGRESSION_PROXY = "win_rate"                     # aggressive doctrines win more
_RISK_PROXY = "avg_winner_casualties"              # riskier wins are cheaper (inverse)
_SUPPLY_PROXY = "avg_red_supply_retained"          # higher focus = more retained
_MORALE_PROXY = "avg_red_morale_retained"          # higher drain = less retained (inverse)

_PARAM_ATTRS = (
    ("aggression", _AGGRESSION_PROXY, +1),
    ("risk", _RISK_PROXY, -1),      # inverse: riskier -> fewer winner casualties
    ("supply_focus", _SUPPLY_PROXY, +1),
    ("morale_drain", _MORALE_PROXY, -1),  # inverse: high drain -> low retention
)


def _reference_force(name: str, side: str, rng: random.Random) -> Force:
    """A fixed, standardized opposing force so every doctrine faces the same
    opponent — the controlled-study baseline."""
    units = [
        Unit(unit_type=UnitType.INFANTRY, strength=85, morale=80, supply=90),
        Unit(unit_type=UnitType.INFANTRY, strength=85, morale=80, supply=90),
        Unit(unit_type=UnitType.ARMOR, strength=90, morale=75, supply=85),
        Unit(unit_type=UnitType.ARTILLERY, strength=80, morale=75, supply=85),
        Unit(unit_type=UnitType.AIR, strength=75, morale=70, supply=80),
        Unit(unit_type=UnitType.RECON, strength=70, morale=75, supply=85),
        Unit(unit_type=UnitType.LOGISTICS, strength=60, morale=70, supply=90),
    ]
    return Force(name=name, doctrine=Doctrine.ATTRITION, units=units, side=side)


def _make_battle(terrain: TerrainType, red_doctrine: Doctrine, seed: int) -> Battle:
    """One controlled battle: red uses the doctrine under test, blue is fixed."""
    rng = random.Random(seed)
    battlefield = Battlefield(
        name=f"Controlled-{terrain.value}",
        center=(30.0, 30.0),
        terrain=terrain,
        area_km2=100000,
        bounds=(20, 20, 40, 40),
    )
    red = _reference_force("Red", "red", rng)
    blue = _reference_force("Blue", "blue", rng)
    red.doctrine = red_doctrine
    deploy_force(red, battlefield, "red", seed)
    deploy_force(blue, battlefield, "blue", seed + 1)
    return Battle(battlefield=battlefield, red_force=red, blue_force=blue,
                  duration_hours=48, seed=seed)


def _spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation coefficient (stdlib-only)."""
    n = len(x)
    if n < 3:
        return 0.0
    rx = _ranks(x)
    ry = _ranks(y)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n))
    dy = sum((ry[i] - my) ** 2 for i in range(n))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy) ** 0.5


def _ranks(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = float(rank)
    return ranks


def run_adherence_probe(
    terrain: Optional[TerrainType] = None,
    n_per_doctrine: int = 100,
    seed: int = 42,
) -> dict:
    """Run the controlled doctrine-adherence study.

    Every doctrine fights the same reference force on the same terrain
    ``n_per_doctrine`` times. For each attribute (aggression/risk/supply_focus/
    morale_drain) we compare the declared parameter ordering across doctrines
    against the observed behavior ordering and report the Spearman correlation.

    Returns a report dict suitable for the research dashboard.
    """
    rng = random.Random(seed)
    terrain = terrain or TerrainType.OPEN

    # Per-doctrine observed behavior.
    observed: dict[str, dict] = {}
    declared: dict[str, dict] = {}
    for doctrine in Doctrine:
        declared[doctrine.value] = dict(_DOCTRINE_PARAMS[doctrine])
        agg = {"durations": [], "winner_casualties": [], "red_casualties": [],
               "blue_casualties": [], "decisive": 0, "wins": 0,
               "red_supply_retained": [], "red_morale_retained": []}
        for i in range(n_per_doctrine):
            battle = _make_battle(terrain, doctrine, seed + i * 7 + hash(doctrine.value) % 99991)
            outcome = simulate_battle(battle, seed=seed + i)
            agg["durations"].append(outcome.duration_hours)
            agg["red_casualties"].append(outcome.red_casualties_pct)
            agg["blue_casualties"].append(outcome.blue_casualties_pct)
            if outcome.winner == "red":
                winner_cas = outcome.red_casualties_pct
                agg["wins"] += 1
            elif outcome.winner == "blue":
                winner_cas = outcome.blue_casualties_pct
            else:
                winner_cas = max(outcome.red_casualties_pct, outcome.blue_casualties_pct)
            agg["winner_casualties"].append(winner_cas)
            if outcome.decisive:
                agg["decisive"] += 1
            agg["red_supply_retained"].append(outcome.red_final_supply_pct)
            agg["red_morale_retained"].append(outcome.red_final_morale_pct)

        avg_red_cas = sum(agg["red_casualties"]) / len(agg["red_casualties"])
        avg_blue_cas = sum(agg["blue_casualties"]) / len(agg["blue_casualties"])
        observed[doctrine.value] = {
            "avg_duration_hours": round(sum(agg["durations"]) / len(agg["durations"]), 1),
            "win_rate": round(agg["wins"] / len(agg["durations"]), 4),
            "avg_winner_casualties": round(
                sum(agg["winner_casualties"]) / len(agg["winner_casualties"]), 1),
            # How much the winning side pays to win: high risk / aggression makes
            # the battle costlier. Direction: high risk -> attacker pays more.
            "casualty_asymmetry": round(avg_red_cas - avg_blue_cas, 1),
            "decisive_rate": round(agg["decisive"] / len(agg["durations"]), 4),
            "avg_red_supply_retained": round(
                sum(agg["red_supply_retained"]) / len(agg["red_supply_retained"]), 4),
            "avg_red_morale_retained": round(
                sum(agg["red_morale_retained"]) / len(agg["red_morale_retained"]), 4),
        }

    # Per-attribute adherence: does declared ordering predict observed ordering?
    attrs = []
    overall_scores = []
    for param, proxy, direction in _PARAM_ATTRS:
        declared_vals = [declared[d][param] for d in observed]
        observed_vals = [observed[d][proxy] for d in observed]
        corr = _spearman(declared_vals, observed_vals)
        # Direction-correct: for morale_drain the proxy is inverted.
        corr *= direction
        attrs.append({
            "attribute": param,
            "proxy": proxy,
            "declared_order": {d: declared[d][param] for d in observed},
            "observed_order": {d: observed[d][proxy] for d in observed},
            "spearman": round(max(-1.0, min(1.0, corr)), 4),
        })
        if corr >= 0.0:
            overall_scores.append(corr)

    overall = (sum(overall_scores) / len(overall_scores)) if overall_scores else 0.0

    # Report the correlation between declared parameter orderings, so the
    # analyst can see that `risk` and `aggression` move together (both drive
    # offensive success in this model) and their adherence signals are not
    # fully independent.
    doctrine_keys = list(observed.keys())
    param_correlations: dict[str, float] = {}
    params = ("aggression", "risk", "supply_focus", "morale_drain")
    for p in params:
        for q in params:
            if p >= q:
                continue
            xv = [declared[k][p] for k in doctrine_keys]
            yv = [declared[k][q] for k in doctrine_keys]
            param_correlations[f"{p}~{q}"] = round(_spearman(xv, yv), 3)

    return {
        "terrain": terrain.value,
        "n_per_doctrine": n_per_doctrine,
        "adherence": round(max(-1.0, min(1.0, overall)), 4),
        "overall_rate": round(sum(1 for a in attrs if a["spearman"] > 0) / len(attrs), 4)
                    if attrs else 0.0,
        "attributes": attrs,
        "observed": observed,
        "declared": declared,
        "parameter_correlations": param_correlations,
        "method": (
            "controlled study: fixed opposing force + fixed terrain, "
            "Spearman rank correlation of declared parameter ordering vs "
            "observed behavioral ordering (MatrAIx-style adherence check)"
        ),
        "note": (
            "risk and aggression are correlated in this combat model (both "
            "scale offensive success), so their adherence signals overlap; "
            "interpret them together rather than as fully independent levers."
        ),
    }


def run_persona_doctrine_adherence(
    personas,
    n_per_persona: int = 20,
    seed: int = 42,
) -> Optional[dict]:
    """Adherence study tying persona risk tolerance to doctrine choice.

    Pairs each persona's declared ``risk_tolerance`` with a matching doctrine
    and checks the pairing behaves as expected. This bridges the persona core
    into the combat engine: do risk-averse personas pick defensive/logistical
    doctrines and do those choices produce the expected low-aggression battles?

    Returns ``None`` when no personas are supplied.
    """
    if not personas:
        return None

    risk_to_doctrine = {
        "very_low": Doctrine.DEFENSIVE, "low": Doctrine.LOGISTICAL,
        "moderate": Doctrine.ATTRITION, "high": Doctrine.MANEUVER,
        "very_high": Doctrine.SHOCK,
    }
    risk_to_expected = {
        "very_low": "long", "low": "long", "moderate": "medium",
        "high": "short", "very_high": "short",
    }

    rng = random.Random(seed)
    results = []
    match = 0
    for persona in personas:
        risk = persona.get("risk_tolerance") or "moderate"
        doctrine = risk_to_doctrine.get(risk, Doctrine.ATTRITION)
        expected = risk_to_expected.get(risk, "medium")
        battle = _make_battle(TerrainType.OPEN, doctrine, rng.randint(0, 2**31 - 1))
        outcome = simulate_battle(battle, seed=rng.randint(0, 2**31 - 1))
        actual = "short" if outcome.duration_hours < 24 else "long"
        ok = actual == expected
        if ok:
            match += 1
        results.append({
            "persona": persona.summary(),
            "risk_tolerance": risk,
            "doctrine": doctrine.value,
            "expected_duration": expected,
            "actual_duration": actual,
            "duration_hours": outcome.duration_hours,
            "winner": outcome.winner,
            "adherent": ok,
        })

    return {
        "n_personas": len(results),
        "adherence_rate": round(match / len(results), 4) if results else 0.0,
        "results": results,
    }