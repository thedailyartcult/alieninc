"""Kriegspiel refinement tests — doctrine adherence probes + BH-gated learning.

Verifies the MatrAIx-style discipline added to the combat engine:
  1. The controlled adherence probe measures whether each doctrine's declared
     parameter profile actually produces distinct battle behavior.
  2. Self-improvement now gates parameter rewrites behind a two-proportion
     z-test plus Benjamini-Hochberg correction, so noise can't drive
     "learning".
  3. Battle outcomes carry final supply/morale state for the probes.
  4. The breakthrough mechanic lets high-aggression doctrines win (Shock is
     viable against attrition, not a guaranteed loss), and a breakthrough is
     recorded on the outcome.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.kriegspiel.models import TerrainType, Doctrine
from engines.kriegspiel.combat import simulate_battle, _DOCTRINE_PARAMS
from engines.kriegspiel.adherence import (
    run_adherence_probe, run_persona_doctrine_adherence,
)
from engines.kriegspiel.scenarios import create_default_battle


def test_battle_outcome_carries_final_state():
    battle = create_default_battle(seed=42)
    outcome = simulate_battle(battle, seed=7)
    assert 0.0 <= outcome.red_final_supply_pct <= 1.0
    assert 0.0 <= outcome.red_final_morale_pct <= 1.0
    assert 0.0 <= outcome.blue_final_supply_pct <= 1.0
    assert 0.0 <= outcome.blue_final_morale_pct <= 1.0


def test_adherence_probe_returns_full_report():
    report = run_adherence_probe(terrain=TerrainType.OPEN, n_per_doctrine=30, seed=7)
    assert report["terrain"] == "open"
    assert report["n_per_doctrine"] == 30
    assert len(report["attributes"]) == 4
    assert len(report["observed"]) == len(list(Doctrine))
    for attr in report["attributes"]:
        assert attr["attribute"] in ("aggression", "risk", "supply_focus", "morale_drain")
        assert -1.0 <= attr["spearman"] <= 1.0
        assert "win_rate" in report["observed"]["shock"]
        assert "casualty_asymmetry" in report["observed"]["shock"]
    assert -1.0 <= report["adherence"] <= 1.0
    assert 0.0 <= report["overall_rate"] <= 1.0


def test_doctrine_behavioral_signatures_differ():
    """The whole point of the probe: doctrines must not all behave alike.
    After the tactical-deployment + engagement rework, the combat model is
    aggression-coherent: Shock (aggression 0.95) wins far more than Defensive
    (aggression 0.3), and aggressive doctrines win with fewer casualties."""
    report = run_adherence_probe(terrain=TerrainType.OPEN, n_per_doctrine=60, seed=11)
    shock = report["observed"]["shock"]
    defensive = report["observed"]["defensive"]
    # Shock is declared far more aggressive -> it must win more.
    assert shock["win_rate"] > defensive["win_rate"]
    # An effective aggressive doctrine wins cheaply -> Shock pays fewer
    # casualties to win than a losing defensive doctrine. Allow a small
    # tolerance (±2) for stochastic variance with 60 scenarios per doctrine.
    assert shock["avg_winner_casualties"] <= defensive["avg_winner_casualties"] + 2


def test_risk_proxy_is_meaningful_not_constant():
    """Regression guard for the risk→decisiveness anomaly: the risk proxy must
    not be a near-constant column (decisive_rate ~0 in this model), which made
    the old Spearman meaningless. After the rework, aggression predicts win rate
    with Spearman ~1.0, and the risk proxy (winner casualties, inverted) must
    vary and register a directionally-correct signal."""
    report = run_adherence_probe(terrain=TerrainType.OPEN, n_per_doctrine=60, seed=21)
    # Aggression must strongly predict win rate (the core claim of the rework).
    agg_attr = next(a for a in report["attributes"] if a["attribute"] == "aggression")
    assert agg_attr["proxy"] == "win_rate"
    assert agg_attr["spearman"] > 0.6
    # The risk proxy must vary across doctrines.
    avcs = {d: o["avg_winner_casualties"] for d, o in report["observed"].items()}
    assert max(avcs.values()) - min(avcs.values()) > 2.0


def test_persona_doctrine_adherence_returns_none_for_empty():
    assert run_persona_doctrine_adherence([], seed=1) is None


def test_shock_is_viable_vs_attrition():
    """Regression guard for the doctrine balance fix: Shock (highest aggression)
    must not be a guaranteed loss against attrition. It wins a meaningful share
    now that its self-attrition is balanced against its aggression."""
    from engines.kriegspiel.models import Force, Battle, Battlefield, Unit, UnitType
    from engines.kriegspiel.geography import deploy_force
    import random

    def make_battle(seed):
        rng = random.Random(seed)
        bf = Battlefield("Test", (30, 30), TerrainType.OPEN, 100000, (20, 20, 40, 40))
        def force(name, side):
            units = [Unit(UnitType.INFANTRY, 85, 80, 90), Unit(UnitType.INFANTRY, 85, 80, 90),
                     Unit(UnitType.ARMOR, 90, 75, 85), Unit(UnitType.ARTILLERY, 80, 75, 85),
                     Unit(UnitType.AIR, 75, 70, 80), Unit(UnitType.RECON, 70, 75, 85),
                     Unit(UnitType.LOGISTICS, 60, 70, 90)]
            return Force(name, doctrine=Doctrine.ATTRITION, units=units, side=side)
        red = force("Red", "red"); blue = force("Blue", "blue")
        red.doctrine = Doctrine.SHOCK; blue.doctrine = Doctrine.ATTRITION
        deploy_force(red, bf, "red", seed); deploy_force(blue, bf, "blue", seed + 1)
        return Battle(bf, red, blue, objective="x", duration_hours=48, seed=seed)

    wins = 0
    n = 200
    for i in range(n):
        if simulate_battle(make_battle(i), seed=i).winner == "red":
            wins += 1
    # Shock should win a meaningful share (well above the old ~0.0%).
    assert wins / n > 0.15


def test_breakthrough_is_recorded_on_outcome():
    """The breakthrough mechanic must populate BattleOutcome.breakthrough_by
    when a high-breakthrough doctrine converts a local edge into a decisive
    penetration."""
    from engines.kriegspiel.models import Force, Battle, Battlefield, Unit, UnitType
    from engines.kriegspiel.geography import deploy_force
    import random

    # Give Shock a clear force advantage so it reliably breaks through.
    def make_battle(seed):
        rng = random.Random(seed)
        bf = Battlefield("Test", (30, 30), TerrainType.OPEN, 100000, (20, 20, 40, 40))
        red_units = [Unit(UnitType.INFANTRY, 95, 95, 95) for _ in range(6)]
        blue_units = [Unit(UnitType.INFANTRY, 60, 50, 60) for _ in range(3)]
        red = Force("Red", Doctrine.SHOCK, red_units, "red")
        blue = Force("Blue", Doctrine.ATTRITION, blue_units, "blue")
        deploy_force(red, bf, "red", seed); deploy_force(blue, bf, "blue", seed + 1)
        return Battle(bf, red, blue, objective="x", duration_hours=48, seed=seed)

    any_breakthrough = False
    for i in range(60):
        o = simulate_battle(make_battle(i), seed=i)
        if o.breakthrough_by:
            any_breakthrough = True
            assert o.breakthrough_by in ("red", "blue")
            assert o.decisive is True
            break
    assert any_breakthrough, "expected at least one breakthrough with a strong Shock force"


def test_persona_doctrine_adherence_runs():
    from sims_core.persona import sample_cohort
    personas = sample_cohort(5, seed=42)
    report = run_persona_doctrine_adherence(personas, n_per_persona=3, seed=7)
    assert report is not None
    assert report["n_personas"] == 5
    assert 0.0 <= report["adherence_rate"] <= 1.0
    assert len(report["results"]) == 5


def test_self_improve_runs_bh_gate(tmp_path):
    """self_improve with sparse cells must not crash, and it must record the
    gate even when nothing is significant."""
    from engines.kriegspiel.learning import DoctrinePerformanceTracker

    tracker = DoctrinePerformanceTracker(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "log.jsonl",
    )
    changes = tracker.self_improve()
    assert isinstance(changes, list)
    history = tracker.bh_gate_history()
    assert history["fdr"] == 0.10
    assert history["hypotheses_tested"] == 0  # no data -> no hypotheses
    assert history["gates_ran"] == 0


def test_self_improve_applies_only_surviving_changes(tmp_path):
    """With a deliberately huge, significant difference, the BH gate must let
    the change through and record p-value evidence on the ParamChange."""
    from engines.kriegspiel.learning import DoctrinePerformanceTracker
    from sims_core.stats import two_proportion_z, benjamini_hochberg

    tracker = DoctrinePerformanceTracker(
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "log.jsonl",
    )
    # Seed a (shock, open) cell with a clearly poor win rate vs a strong
    # (defensive, open) cell with many samples.
    shock_cell = tracker._cells[("shock", "open")]
    shock_cell.wins = 5
    shock_cell.total = 100
    def_cell = tracker._cells[("defensive", "open")]
    def_cell.wins = 80
    def_cell.total = 100

    z, p = two_proportion_z(0.05, 100, 0.8, 100)
    assert p < 1e-9
    rejected, _ = benjamini_hochberg([p], fdr=0.10)
    assert rejected == [True]

    changes = tracker.self_improve()
    assert changes, "expected a surviving change to be applied"
    for ch in changes:
        assert ch.survived_bh is True
        assert ch.p_value < 0.05
        assert ch.fdr_gate >= 0.0  # threshold can round to 0.0 for p=0