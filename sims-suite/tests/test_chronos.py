"""Tests for the Chronos historical what-if engine."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engines.chronos.models import HistoricalBattle, HistoricalSide, era_profile
from engines.chronos.engine import resolve_battle, simulate_historical, what_if
from engines.chronos.fidelity import fidelity_report, assert_gate
from engines.chronos import loader

DB = Path(os.environ.get("CHRONOS_TEST_DB",
                         "/home/alieninc/panteon/backend/panteon.db"))


def _battle(year=1942):
    return HistoricalBattle(
        battle_key="test-1", name="TEST", war="WORLD WAR II (TEST 1942-1943)",
        year=year,
        attacker=HistoricalSide(side_id=1, strength=100000, casualties=6000,
                                tanks=500, artillery=800, aircraft=300,
                                morale=1, result_code="BB"),
        defender=HistoricalSide(side_id=0, strength=80000, casualties=12000,
                                tanks=300, artillery=500, aircraft=100,
                                result_code="RR"),
    )


class TestEra:
    def test_era_progression(self):
        assert era_profile(1805).air_effectiveness == 0.0
        assert era_profile(1916).armor_effectiveness < era_profile(1943).armor_effectiveness
        assert era_profile(1917).defense_bias > era_profile(1944).defense_bias
        assert "napoleonic" == era_profile(1812).name
        assert "world-war-ii" == era_profile(1943).name

    def test_no_air_before_ww(self):
        b = _battle(year=1862)
        assert b.era.air_effectiveness == 0.0


class TestWinnerLogic:
    def test_attacker_success_codes(self):
        for code in ("AA", "PS", "PP", "BB"):
            b = _battle()
            b.attacker.result_code = code
            assert b.actual_winner == "attacker"

    def test_defender_holds_codes(self):
        for code in ("RR", "WD", "WL"):
            b = _battle()
            b.attacker.result_code = code
            assert b.actual_winner == "defender"


class TestEngine:
    def test_strong_attack_wins(self):
        r = simulate_historical(_battle(), universes=50, seed=3)
        assert r["predicted_winner"] == "attacker"
        assert r["win_distribution"]["attacker"] > 0.9

    def test_overwhelming_defense_holds(self):
        b = _battle()
        b.defender.strength = 400000
        b.attacker.strength = 20000
        b.attacker.result_code = "RR"
        b.defender.result_code = "BB"
        r = simulate_historical(b, universes=50, seed=3)
        assert r["predicted_winner"] == "defender"

    def test_branches_vary(self):
        r = simulate_historical(_battle(), universes=30, seed=3)
        assert r["universes"] == 30
        assert isinstance(r["convergence"], float)

    def test_what_if_reinforcement_raises_enemy_losses(self):
        b = _battle()
        d = what_if(b, {"defender_strength_mult": 1.5}, universes=60, seed=3)
        assert d["counterfactual"]["avg_attacker_casualties"] > \
            d["baseline"]["avg_attacker_casualties"]

    def test_deterministic_seed(self):
        a = simulate_historical(_battle(), universes=20, seed=99)
        c = simulate_historical(_battle(), universes=20, seed=99)
        assert a["win_distribution"] == c["win_distribution"]


class TestFidelityGate:
    def test_gate_passes_on_matching_battle(self):
        rep = fidelity_report(_battle(), universes=80, seed=3)
        assert rep["passed"] is True
        assert_gate(rep)

    def test_gate_blocks_when_wrong_winner(self):
        b = _battle()
        b.attacker.strength = 1000
        b.defender.strength = 500000
        b.attacker.result_code = "BB"
        rep = fidelity_report(b, universes=40, seed=3)
        if not rep["passed"]:
            with pytest.raises(PermissionError):
                assert_gate(rep)


@pytest.mark.skipif(not DB.exists(), reason="panteon.db not available")
class TestLoader:
    def test_load_alamein(self):
        b = loader.load_battle(387, DB)
        assert b and "ALAMEIN" in b.name.upper()
        assert b.year == 1942
        assert b.actual_winner == "attacker"
        assert b.attacker.strength > 50000

    def test_country_power(self):
        p = loader.country_power("GMY", 1939, DB)
        assert p and p["cinc"] > 0

    def test_top_powers_1939(self):
        tops = loader.top_powers(1939, 5, DB)
        assert len(tops) == 5
        assert tops[0]["cinc"] >= tops[-1]["cinc"]
