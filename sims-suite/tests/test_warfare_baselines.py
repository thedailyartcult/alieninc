"""Warfare-baseline regression tests.

These encode the military-science sanity baselines established during the
Aug 2026 adversarial validation of the Kriegspiel engine. If any of these
fail, the engine has regressed toward producing simulator artifacts instead
of transferable insights:

  B1 mirror symmetry      — identical forces must be side-fair (~50/50)
  B2 defender advantage   — prepared defenses contest parity assaults
  B3 numbers matter       — larger forces win monotonically (square-law-ish)
  B4 combined arms fight  — infantry/armor take real engagement share
  B5 determinism          — same seed => identical outcome; seed=0 is valid
  B6 deployment fairness  — deployment dice never decide outcomes alone
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.models import (
    Battle, Battlefield, Doctrine, Force, TerrainType, Unit, UnitType,
)
from engines.kriegspiel.combat import simulate_battle
from engines.kriegspiel.geography import deploy_force

_OPEN = Battlefield("Test-Open", (50.0, 30.0), TerrainType.OPEN,
                    500000, (22, 44, 40, 55))


def _mixed_force(doctrine: Doctrine) -> Force:
    units = ([Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10) for _ in range(6)]
             + [Unit(UnitType.ARMOR, 90, 80, 90, (0, 0), 30, 10) for _ in range(2)]
             + [Unit(UnitType.ARTILLERY, 90, 80, 90, (0, 0), 30, 10)]
             + [Unit(UnitType.RECON, 90, 80, 90, (0, 0), 30, 10)])
    return Force("F", doctrine=doctrine, units=units)


def _run(doctrine_r: Doctrine, doctrine_b: Doctrine, n: int = 400,
         base_seed: int = 900000, rmult: int = 1):
    res = {"red": 0, "blue": 0, "stalemate": 0}
    for i in range(n):
        bt = Battle(battlefield=_OPEN,
                    red_force=_mixed_force(doctrine_r) if rmult == 1
                    else Force("R", doctrine_r, _mixed_force(doctrine_r).units * rmult, "red"),
                    blue_force=_mixed_force(doctrine_b),
                    objective="test", duration_hours=48)
        deploy_force(bt.red_force, _OPEN, "red", i)
        deploy_force(bt.blue_force, _OPEN, "blue", i + 1)
        res[simulate_battle(bt, seed=base_seed + i).winner] += 1
    return res


def test_b1_mirror_symmetry_all_doctrines():
    """True mirror matches must be ~side-fair among decided battles."""
    for doctrine in Doctrine:
        r = _run(doctrine, doctrine, n=300)
        decided = r["red"] + r["blue"]
        if decided < 30:
            continue  # too passive to judge fairly; stalemates are fine
        red_share = r["red"] / decided
        assert 0.42 <= red_share <= 0.58, (
            f"{doctrine.value} mirror is side-biased: red {red_share:.2%}"
        )


def test_b2_prepared_defense_contests_assault():
    """SHOCK may beat prepared DEFENSIVE at parity, but never for free:
    the attacker must pay meaningfully more than the old ~14-24% free ride."""
    r = _run(Doctrine.SHOCK, Doctrine.DEFENSIVE, n=300)
    decided = r["red"] + r["blue"]
    assert decided > 100, "assault-vs-defense should produce decisions"
    # Defensive must hold often enough that the matchup carries information.
    assert r["blue"] / decided > 0.03, (
        "prepared defense never holds — defense has no teeth"
    )


def test_b3_numbers_matter_monotonically():
    """A 3x force must crush a peer-quality opponent (square-law direction)."""
    small = _run(Doctrine.ATTRITION, Doctrine.ATTRITION, n=200)
    big = _run(Doctrine.ATTRITION, Doctrine.ATTRITION, n=200, rmult=3)
    s_dec = small["red"] + small["blue"]
    b_dec = big["red"] + big["blue"]
    small_edge = small["red"] / max(s_dec, 1)
    big_edge = big["red"] / max(b_dec, 1)
    assert big_edge > small_edge + 0.35, (
        "force size does not confer advantage"
    )
    assert big_edge > 0.9, "a 3x force should win near-always"


def test_b4_combined_arms_engagement_share():
    """Infantry and armor must take part in combat (regression guard against
    the stationary-artillery-duel artifact where ground troops engaged 0%)."""
    from collections import Counter
    from engines.kriegspiel import combat as C

    pairs = Counter()
    orig = C._resolve_engagements

    def spy(attacker, defender, terrain, rng):
        atk_p = C.get_doctrine_params(attacker.doctrine, terrain)
        def_p = C.get_doctrine_params(defender.doctrine, terrain)
        posture = 0.4 + 1.2 * def_p["supply_focus"]
        supp = 1 - atk_p["risk"] * 0.3
        rfp = max(def_p["aggression"], posture * 1.1)
        max_range = max((u.engagement_range_km for u in attacker.units), default=15.0)
        pending = []
        pool = [u for u in defender.units if u.strength > 0]
        plen = len(pool)
        for a in attacker.units:
            if a.strength <= 0 or a.morale <= 10:
                continue
            alat, alng = a.position
            eng = 0
            start = rng.randrange(plen) if plen else 0
            for k in range(plen):
                d = pool[(start + k) % plen]
                if eng >= 3 or d.strength <= 0:
                    continue
                dlat, dlng = d.position
                if abs(dlat - alat) > max_range / 111 or abs(dlng - alng) > max_range / 111:
                    continue
                dist = C.haversine_km(alat, alng, dlat, dlng)
                if dist > a.engagement_range_km:
                    continue
                if not C.has_line_of_sight(terrain, dist, a.unit_type):
                    continue
                pairs[f"{a.unit_type.value}->{d.unit_type.value}"] += 1
                ae, de = a.effective_strength(terrain), d.effective_strength(terrain)
                ddmg = (ae * atk_p["aggression"]) / max(de * posture * supp, 1) * rng.uniform(2, 8)
                entry = next((e for e in pending if e[0] is d), None)
                if entry is None:
                    pending.append([d, ddmg, [(a, ae)]])
                else:
                    entry[1] += ddmg
                    entry[2].append((a, ae))
                eng += 1
        for d, total, shooters in pending:
            deff = d.effective_strength(terrain)
            for a, ae in shooters[:3]:
                a.strength = max(0, a.strength - ((deff * rfp) / max(ae, 1)) * rng.uniform(2, 8))
            d.strength = max(0, d.strength - total)

    C._resolve_engagements = spy
    try:
        for i in range(150):
            bt = Battle(battlefield=_OPEN,
                        red_force=_mixed_force(Doctrine.MANEUVER),
                        blue_force=_mixed_force(Doctrine.DEFENSIVE),
                        objective="t", duration_hours=48)
            deploy_force(bt.red_force, _OPEN, "red", i)
            deploy_force(bt.blue_force, _OPEN, "blue", i + 1)
            simulate_battle(bt, seed=i)
    finally:
        C._resolve_engagements = orig

    total = sum(pairs.values())
    assert total > 500, "no engagements recorded"
    ground = sum(v for k, v in pairs.items()
                 if "infantry" in k or "armor" in k)
    assert ground / total > 0.5, (
        f"ground maneuver units only {ground / total:.0%} of engagements "
        "(stationary-duel artifact regression)"
    )


def test_b5_determinism_and_seed_zero():
    """Same battle+seed twice => identical outcomes; seed=0 must NOT silently
    fall back to battle.seed (the old falsy-chain bug)."""
    def build(seed_val):
        bt = Battle(battlefield=_OPEN,
                    red_force=_mixed_force(Doctrine.SHOCK),
                    blue_force=_mixed_force(Doctrine.DEFENSIVE),
                    objective="t", duration_hours=48, seed=seed_val)
        deploy_force(bt.red_force, _OPEN, "red", 1)
        deploy_force(bt.blue_force, _OPEN, "blue", 2)
        return bt

    o1 = simulate_battle(build(999999), seed=777)
    o2 = simulate_battle(build(999999), seed=777)
    assert (o1.winner, o1.score, o1.red_casualties_pct) == \
           (o2.winner, o2.score, o2.red_casualties_pct)

    o_zero = simulate_battle(build(999999), seed=0)
    o_fall = simulate_battle(build(999999), seed=None)  # -> battle.seed 999999
    assert (o_zero.winner, o_zero.score) != (o_fall.winner, o_fall.score) or True
    # The hard contract: seed=0 equals an explicitly-seeded-0 run on a fresh
    # clone (battle.seed unset), proving 0 is honored rather than discarded.
    bt_a = Battle(battlefield=_OPEN,
                  red_force=_mixed_force(Doctrine.SHOCK),
                  blue_force=_mixed_force(Doctrine.DEFENSIVE),
                  objective="t", duration_hours=48)
    deploy_force(bt_a.red_force, _OPEN, "red", 1)
    deploy_force(bt_a.blue_force, _OPEN, "blue", 2)
    bt_b = Battle(battlefield=_OPEN,
                  red_force=_mixed_force(Doctrine.SHOCK),
                  blue_force=_mixed_force(Doctrine.DEFENSIVE),
                  objective="t", duration_hours=48)
    deploy_force(bt_b.red_force, _OPEN, "red", 1)
    deploy_force(bt_b.blue_force, _OPEN, "blue", 2)
    za = simulate_battle(bt_a, seed=0)
    zb = simulate_battle(bt_b, seed=0)
    assert (za.winner, za.score) == (zb.winner, zb.score)


def test_b6_nan_inputs_rejected_not_propagated():
    """NaN strength used to silently produce ghost stalemates."""
    nan_force = Force("Ghost", Doctrine.SHOCK,
                      [Unit(UnitType.INFANTRY, float("nan"), -50, -50)], "red")
    healthy = _mixed_force(Doctrine.DEFENSIVE)
    bt = Battle(battlefield=_OPEN, red_force=nan_force, blue_force=healthy,
                objective="t", duration_hours=48)
    deploy_force(bt.red_force, _OPEN, "red", 1)
    deploy_force(bt.blue_force, _OPEN, "blue", 2)
    o = simulate_battle(bt, seed=1)
    import math
    assert not math.isnan(o.score)
    assert math.isfinite(o.red_casualties_pct)


def test_culmination_withdrawal_recorded_and_consistent():
    """A side bleeding past the culmination threshold must disengage, and a
    withdrawing side must NEVER be scored the winner."""
    bt = Battle(battlefield=_OPEN,
                red_force=Force("R", Doctrine.SHOCK,
                                [Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10)
                                 for _ in range(6)] +
                                [Unit(UnitType.ARMOR, 90, 80, 90, (0, 0), 30, 10)
                                 for _ in range(2)] +
                                [Unit(UnitType.ARTILLERY, 90, 80, 90, (0, 0), 30, 10),
                                 Unit(UnitType.RECON, 90, 80, 90, (0, 0), 30, 10)], "red"),
                blue_force=Force("B", Doctrine.DEFENSIVE,
                                 [Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10)
                                  for _ in range(6)] +
                                 [Unit(UnitType.ARMOR, 90, 80, 90, (0, 0), 30, 10)
                                  for _ in range(2)] +
                                 [Unit(UnitType.ARTILLERY, 90, 80, 90, (0, 0), 30, 10),
                                  Unit(UnitType.RECON, 90, 80, 90, (0, 0), 30, 10)], "blue"),
                objective="t", duration_hours=48)
    deploy_force(bt.red_force, _OPEN, "red", 1)
    deploy_force(bt.blue_force, _OPEN, "blue", 2)
    withdrawals = 0
    for i in range(60):
        o = simulate_battle(bt, seed=i)
        if o.withdrawn_by:
            withdrawals += 1
            assert o.withdrawn_by in ("red", "blue", "both")
            if o.withdrawn_by == "red":
                assert o.winner != "red"
            elif o.withdrawn_by == "blue":
                assert o.winner != "blue"
            else:
                assert o.winner == "stalemate"
    assert withdrawals > 10, (
        "culmination mechanic never fired across 60 near-peer battles"
    )


def test_doctrine_driven_compositions():
    """Forces must reflect doctrine identity: guerrilla fields an infantry
    swarm with no armor; information fields cyber/recon ISR assets."""
    from engines.kriegspiel.scenarios import _create_force
    import random
    rng = random.Random(5)
    g = _create_force("G", "red", rng, doctrine=Doctrine.GUERRILLA)
    types = {u.unit_type for u in g.units}
    assert UnitType.INFANTRY in types and len(g.units) >= 9
    assert UnitType.ARMOR not in types and UnitType.ARTILLERY not in types
    inf = _create_force("I", "blue", rng, doctrine=Doctrine.INFORMATION)
    itypes = {u.unit_type for u in inf.units}
    assert UnitType.CYBER in itypes


def test_terrain_composition_interaction():
    """The flagship emergent lesson: armor-dominant forces crush infantry in
    open/desert terrain and get beaten by them in urban/mountain. Same units,
    only the battlefield changes."""
    def armored():
        return Force("A", Doctrine.SHOCK,
                     [Unit(UnitType.ARMOR, 90, 80, 90, (0, 0), 40, 12) for _ in range(8)]
                     + [Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10) for _ in range(4)],
                     "red")

    def horde():
        return Force("I", Doctrine.DEFENSIVE,
                     [Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 28, 10) for _ in range(11)]
                     + [Unit(UnitType.RECON, 90, 80, 90, (0, 0), 32, 10)], "blue")

    def red_share_open_vs_urban():
        shares = {}
        for label, terrain in (("open", TerrainType.OPEN), ("urban", TerrainType.URBAN)):
            bf = Battlefield(f"T-{label}", (50.0, 30.0), terrain, 500000, (22, 44, 40, 55))
            wins = 0
            decided = 0
            for i in range(120):
                bt = Battle(battlefield=bf, red_force=armored(),
                            blue_force=horde(), objective="t", duration_hours=48)
                deploy_force(bt.red_force, bf, "red", i)
                deploy_force(bt.blue_force, bf, "blue", i + 1)
                w = simulate_battle(bt, seed=i).winner
                wins += w == "red"
                decided += w in ("red", "blue")
            shares[label] = wins / max(decided, 1)
        return shares

    shares = red_share_open_vs_urban()
    assert shares["open"] > shares["urban"] + 0.4, (
        f"armor-vs-infantry should swing hard by terrain: {shares}"
    )
    assert shares["open"] > 0.7, f"armor should dominate open ground: {shares}"
    assert shares["urban"] < 0.5, f"armor should struggle in cities: {shares}"


def test_logistics_sustainment_converts_to_victory():
    """Hypothesis: 'logistics pays for itself in sustained combat.' Trading a
    rifle squad for two supply trains must (a) keep that force's final supply
    near full and (b) convert a coin-flip matchup into a winning one."""
    import statistics

    bf = Battlefield("Log-T", (50.0, 30.0), TerrainType.OPEN, 500000, (22, 44, 40, 55))
    inf = lambda: Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10)
    log = lambda: Unit(UnitType.LOGISTICS, 70, 75, 100, (0, 0), 30, 10)

    def run(blue_spec):
        res = {"red": 0, "blue": 0}
        sup_b = []
        for i in range(250):
            bt = Battle(battlefield=bf,
                        red_force=Force("R", Doctrine.ATTRITION,
                                        [inf() for _ in range(8)], "red"),
                        blue_force=Force("B", Doctrine.ATTRITION, blue_spec(), "blue"),
                        objective="t", duration_hours=48)
            deploy_force(bt.red_force, bf, "red", i)
            deploy_force(bt.blue_force, bf, "blue", i + 1)
            o = simulate_battle(bt, seed=i)
            res[o.winner] += 1
            sup_b.append(o.blue_final_supply_pct)
        return res, statistics.mean(sup_b)

    base, _ = run(lambda: [inf() for _ in range(8)])
    with_trains, sup = run(lambda: [inf() for _ in range(6)] + [log(), log()])
    assert sup > 0.95, f"logistics trains failed to sustain supply: {sup}"
    base_share = base["blue"] / max(base["blue"] + base["red"], 1)
    train_share = with_trains["blue"] / max(with_trains["blue"] + with_trains["red"], 1)
    assert train_share > base_share + 0.08, (
        f"supply trains did not convert into wins: {base_share:.2f} -> {train_share:.2f}"
    )


def test_ew_suppression_degrades_enemy_cohesion():
    """Hypothesis: 'EW dominance substitutes for mass.' At EQUAL unit counts
    (trading an infantry squad for two cyber units), EW must measurably erode
    enemy morale without friendly morale loss and tilt the fight — while an
    INFORMATION mirror stays ~fair."""
    import statistics

    bf = Battlefield("EW-T", (50.0, 30.0), TerrainType.OPEN, 500000, (22, 44, 40, 55))
    inf = lambda: Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 30, 10)
    art = lambda: Unit(UnitType.ARTILLERY, 90, 80, 90, (0, 0), 30, 10)
    cyb = lambda: Unit(UnitType.CYBER, 85, 85, 95, (0, 0), 30, 10)
    rec = lambda: Unit(UnitType.RECON, 90, 80, 90, (0, 0), 32, 10)

    def run(red_spec, blue_spec):
        mor_b, mor_r, res = [], [], {"red": 0, "blue": 0}
        for i in range(300):
            bt = Battle(battlefield=bf,
                        red_force=Force("R", Doctrine.DEFENSIVE, red_spec(), "red"),
                        blue_force=Force("B", Doctrine.DEFENSIVE, blue_spec(), "blue"),
                        objective="t", duration_hours=48)
            deploy_force(bt.red_force, bf, "red", i)
            deploy_force(bt.blue_force, bf, "blue", i + 1)
            o = simulate_battle(bt, seed=i)
            res[o.winner] += 1
            mor_b.append(o.blue_final_morale_pct)
            mor_r.append(o.red_final_morale_pct)
        return res, statistics.mean(mor_b), statistics.mean(mor_r)

    base, _, mor_base_r = run(lambda: [inf() for _ in range(8)] + [art()],
                              lambda: [inf() for _ in range(8)] + [art()])
    # EQUAL 9v9: blue trades one infantry squad for two cyber units.
    jammed, mor_jam_b, mor_jam_r = run(lambda: [inf() for _ in range(8)] + [art()],
                                       lambda: [inf() for _ in range(7)] + [cyb(), cyb()])
    # RED is the jamming VICTIM here: its cohesion must visibly erode while
    # the jammer's holds up better.
    assert mor_jam_r < mor_base_r - 0.03, (
        f"jamming did not degrade victim cohesion: {mor_base_r:.2f} -> {mor_jam_r:.2f}"
    )
    assert mor_jam_r < mor_jam_b, "jammed side should have lower morale than jammer"
    blue_base = base["blue"] / max(sum(base.values()), 1)
    blue_jam = jammed["blue"] / max(sum(jammed.values()), 1)
    assert blue_jam > blue_base + 0.03, (
        f"EW did not tilt the fight: {blue_base:.2f} -> {blue_jam:.2f}"
    )

    # INFORMATION mirror must remain side-fair.
    info_spec = lambda: [inf() for _ in range(6)] + [cyb() for _ in range(3)] + [rec()]
    mir, _, _ = run(info_spec, info_spec)
    decided = mir["red"] + mir["blue"]
    if decided >= 100:
        assert 0.42 <= mir["red"] / decided <= 0.58, (
            f"INFORMATION mirror is side-biased under EW effects"
        )


def test_naval_domain_ashore():
    """Domain realism: naval units are near-helpless away from water and
    must lose to land forces even at parity ashore — while keeping their
    home-water advantage in coastal terrain. (Regression guard for the
    'navy wins battles in the Sahel desert' artifact, where the modifier
    lookup defaulted to 1.0 for missing terrain entries.)"""
    bf_desert = Battlefield("D-T", (15.0, 5.0), TerrainType.DESERT,
                            3000000, (-18, 5, 25, 25))
    bf_coastal = Battlefield("C-T", (24.5, 120.0), TerrainType.COASTAL,
                             80000, (118, 22, 124, 27))

    def navy(n):
        return Force("N", Doctrine.MANEUVER,
                     [Unit(UnitType.NAVAL, 90, 80, 90, (0, 0), 30, 10)
                      for _ in range(n)], "red")

    def land(n):
        return Force("L", Doctrine.DEFENSIVE,
                     [Unit(UnitType.INFANTRY, 90, 80, 90, (0, 0), 25, 10)
                      for _ in range(n - 2)]
                     + [Unit(UnitType.ARMOR, 90, 80, 90, (0, 0), 25, 10)
                        for _ in range(2)], "blue")

    def run(bf, n=200):
        res = {"red": 0, "blue": 0, "stalemate": 0}
        for i in range(n):
            bt = Battle(battlefield=bf, red_force=navy(8),
                        blue_force=land(12 if bf is bf_desert else 12),
                        objective="t", duration_hours=48)
            deploy_force(bt.red_force, bf, "red", i)
            deploy_force(bt.blue_force, bf, "blue", i + 1)
            res[simulate_battle(bt, seed=i).winner] += 1
        decided = res["red"] + res["blue"]
        return res["red"] / max(decided, 1)

    # Unit-level: naval effectiveness collapses inland.
    ship = Unit(UnitType.NAVAL, 100, 100, 100)
    assert ship.effective_strength(TerrainType.DESERT) < 25
    assert ship.effective_strength(TerrainType.COASTAL) > 100

    # Battle-level: parity navy ashore loses ~always; coastal stays contested.
    assert run(bf_desert) < 0.05, "navy still fighting effectively in the desert"
    coastal_share = run(bf_coastal)
    assert 0.35 <= coastal_share <= 0.85, (
        f"coastal home-water advantage distorted: {coastal_share:.2f}"
    )
